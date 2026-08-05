from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import FixSafety
from mcmr.facts import (
    CallFact,
    ClassFact,
    ExportFact,
    FunctionFact,
    ImportBindingFact,
    ModuleFact,
    NodeRef,
    SourceSpan,
)
from mcmr.plugins import RepositoryTables, fact_table
from mcmr.query import RuleQuery
from mcmr.rules.general import (
    module_class_count,
    module_line_count,
    module_member_count,
    module_statement_count,
    test_module_member_count,
)
from mcmr.rules.python import (
    bypassed_public_import,
    empty_package_initializer,
    explicit_all_only_in_initializer,
    initializer_declaration,
    non_init_reexport_module,
    unused_explicit_export,
)
from mcmr.table import AnalysisSession

from ..support import retained_query, written

if TYPE_CHECKING:
    from pathlib import Path

from .support import export_subject, scalar


def test_module_shape_cases() -> None:
    module = ModuleFact(
        key="module",
        span=SourceSpan(path="src/models.py"),
        physical_line_count=401,
        statement_count=201,
        class_count=9,
        function_count=4,
        has_only_imports_and_all=True,
    )
    assert (
        scalar(retained_query(module, module_line_count)),
        scalar(retained_query(module, module_statement_count)),
        scalar(retained_query(module, module_class_count)),
        scalar(retained_query(module, module_member_count)),
        scalar(retained_query(module, test_module_member_count)),
        scalar(retained_query(module, non_init_reexport_module)),
    ) == (401, 201, 9, 13, 0, 1)
    initializer = module.model_copy(update={"is_package_initializer": True})
    test_module = module.model_copy(
        update={"span": SourceSpan(path="tests/conftest.py"), "is_test": True}
    )
    assert (
        scalar(retained_query(initializer, non_init_reexport_module)),
        scalar(retained_query(test_module, non_init_reexport_module)),
        scalar(retained_query(test_module, module_member_count)),
        scalar(retained_query(test_module, test_module_member_count)),
    ) == (0, 0, 0, 13)


def test_python_initializer_surface_cases() -> None:
    initializer = ModuleFact(
        key="module",
        span=SourceSpan(path="src/package/__init__.py"),
        executable_statement_count=4,
        is_package_initializer=True,
        declares_all=True,
        members=[
            ModuleFact.Member(name="Client", kind="class", source="class Client: ..."),
            ModuleFact.Member(name="connect", kind="function", source="def connect(): ..."),
            ModuleFact.Member(
                name="__getattr__", kind="function", source="def __getattr__(): ..."
            ),
            ModuleFact.Member(name="__dir__", kind="function", source="def __dir__(): ..."),
        ],
    )

    assert scalar(retained_query(initializer, empty_package_initializer)) is False
    assert scalar(retained_query(initializer, explicit_all_only_in_initializer)) is False
    assert (
        scalar(
            retained_query(
                initializer.model_copy(update={"executable_statement_count": 0}),
                empty_package_initializer,
            )
        )
        is True
    )
    module = initializer.model_copy(
        update={
            "span": SourceSpan(path="src/package/client.py"),
            "is_package_initializer": False,
            "all_declarations": [
                NodeRef(
                    id="client.py:all",
                    span=SourceSpan(
                        path="src/package/client.py",
                        start_line=1,
                        end_line=1,
                        end_column=20,
                    ),
                    kind="statement",
                    text='__all__ = ["Client"]',
                )
            ],
        }
    )
    explicit = retained_query(module, explicit_all_only_in_initializer)
    assert explicit.fix is not None
    assert (
        scalar(explicit),
        explicit_all_only_in_initializer.query_fix_safety,
        explicit.fix.rewrites.collect().item(0, "kind"),
        explicit.fix.nodes.collect().item(0, "text"),
    ) == (True, FixSafety.REVIEW, "remove", '__all__ = ["Client"]')


def test_initializer_declaration_moves_to_one_existing_constructed_owner(tmp_path: Path) -> None:
    """The review repair picks a cohesive sibling and preserves exact import requirements."""
    written(
        tmp_path,
        {
            "package/__init__.py": """from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcmr.facts import Fact

from .schema import SchemaStrategy
from .vocabulary import vocabulary


@cache
def facts_of[FactType: Fact](family: type[FactType]) -> FactType:
    return SchemaStrategy(dialect=vocabulary(family)).of(family)
""",
            "package/schema.py": "class SchemaStrategy:\n    pass\n",
            "package/vocabulary.py": "def vocabulary(family):\n    return family\n",
        },
    )
    families = [ModuleFact, FunctionFact, CallFact, ClassFact, ImportBindingFact]
    session = AnalysisSession(tmp_path, suffixes=[".py"], typed_families=families)
    tables = (
        RepositoryTables()
        .add(session.table(ModuleFact))
        .add(session.function_tables())
        .add(session.call_tables())
        .add(session.class_tables())
        .add(session.import_binding_tables())
    )

    result = cast(
        "RuleQuery",
        initializer_declaration.invoke(
            tables,
            settings={},
            dependencies={},
        ),
    )

    assert result.fix is not None
    assert (
        result.values.collect().get_column("integer_value").sum(),
        result.fix.rewrites.collect().get_column("kind").to_list(),
        result.fix.nodes.collect().select("role", "path").rows(),
        set(result.fix.imports.collect().get_column("name")),
    ) == (
        1,
        ["move"],
        [("target", "package/__init__.py"), ("anchor", "package/schema.py")],
        {"cache", "Fact", "vocabulary"},
    )


def test_an_explicit_export_needs_a_repository_consumer() -> None:
    subject = export_subject()
    result = retained_query(subject, unused_explicit_export)

    assert scalar(result) == 1
    assert result.findings is not None and result.fix is not None
    assert (
        "`Engine` explicitly exports `pkg.engine.Engine`"
        in result.findings.rows.collect().item(0, "message")
    )
    assert (
        unused_explicit_export.query_fix_safety,
        result.fix.rewrites.collect().item(0, "kind"),
        result.fix.nodes.collect().item(0, "text"),
    ) == (FixSafety.REVIEW, "remove", '"Engine"')
    used = subject.model_copy(
        update={"public_export": subject.public_export.model_copy(update={"consumer_count": 2})}
    )
    assert scalar(retained_query(used, unused_explicit_export)) == 0


def test_a_public_import_bypass_needs_a_safe_rewrite() -> None:
    subject = export_subject()
    bypass = retained_query(subject, bypassed_public_import)

    assert scalar(bypass) == 1
    assert bypass.findings is not None and bypass.fix is not None
    assert (
        "`pkg.Engine`" in bypass.findings.rows.collect().item(0, "message"),
        bypassed_public_import.query_fix_safety,
        bypass.fix.rewrites.collect().item(0, "source"),
        bypass.fix.nodes.collect().item(0, "text"),
    ) == (True, FixSafety.SAFE, "pkg", "pkg.engine")
    unsafe = retained_query(
        subject.model_copy(
            update={"bypasses": [subject.bypasses[0].model_copy(update={"is_cycle_safe": False})]}
        ),
        bypassed_public_import,
    )
    assert scalar(unsafe) == 1
    assert unsafe.fix is not None
    assert unsafe.fix.rewrites.collect().is_empty()


def test_public_import_bypasses_group_only_identical_rewrites() -> None:
    subject = export_subject()
    first = subject.model_copy(
        update={
            "bypasses": [subject.bypasses[0].model_copy(update={"binding_count": 2})],
        }
    )
    second = subject.model_copy(
        update={
            "key": "export:pkg.Client",
            "public_export": subject.public_export.model_copy(
                update={"name": "Client", "target": "pkg.engine.Client"}
            ),
            "bypasses": [
                subject.bypasses[0].model_copy(
                    update={
                        "name": "Client",
                        "target": "pkg.engine.Client",
                        "expression": "pkg.engine.Client",
                        "binding_count": 2,
                    }
                )
            ],
        }
    )
    grouped = bypassed_public_import.invoke_table(
        fact_table(ExportFact, [first, second]),
        settings={},
        dependencies={},
    )
    assert isinstance(grouped, RuleQuery) and grouped.fix is not None
    assert (
        grouped.fix.rewrites.collect().height,
        grouped.fix.nodes.collect().height,
    ) == (1, 1)

    mixed = bypassed_public_import.invoke_table(
        fact_table(
            ExportFact,
            [
                first,
                second.model_copy(
                    update={
                        "bypasses": [
                            second.bypasses[0].model_copy(update={"replacement_module": "public"})
                        ]
                    }
                ),
            ],
        ),
        settings={},
        dependencies={},
    )
    assert isinstance(mixed, RuleQuery) and mixed.fix is not None
    assert mixed.fix.rewrites.collect().is_empty()
