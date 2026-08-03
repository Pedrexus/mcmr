from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import FixSafety, RuleValue
from mcmr.facts import (
    CallFact,
    ClassFact,
    DirectoryFact,
    ExportBypass,
    ExportFact,
    Fact,
    FunctionFact,
    ImportBindingFact,
    ModuleFact,
    NodeRef,
    PublicExport,
    SourceSpan,
)
from mcmr.query import RuleQuery
from mcmr.rules.general import (
    directory_module_count,
    directory_pathway,
    empty_directories,
    module_class_count,
    module_line_count,
    module_member_count,
    module_statement_count,
    package_depth,
)
from mcmr.rules.python import (
    bypassed_public_import,
    empty_package_initializer,
    explicit_all_only_in_initializer,
    import_module_depth,
    initializer_declaration,
    internal_relative_import,
    non_init_reexport_module,
    project_private_import,
    unused_explicit_export,
    unused_import,
)
from mcmr.table import AnalysisSession, fact_table

from ..support import retained_query, written

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mcmr.table import Table


def scalar(query: RuleQuery, row: int = 0) -> RuleValue:
    """Return one scalar from a direct rule query."""
    values = query.values.collect().row(row, named=True)
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        if values[name] is not None:
            return cast("RuleValue", values[name])
    raise TypeError("the rule emitted no scalar value")


def import_queries(root: Path) -> Mapping[str, RuleQuery]:
    """Parse one import corpus once and run its import rules once each."""
    session = AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[ImportBindingFact.__name__, ExportFact.__name__],
    )
    table = session.import_binding_tables()
    exports = session.table(ExportFact)
    queries: dict[str, RuleQuery] = {}
    for rule in (
        internal_relative_import,
        project_private_import,
        unused_import,
        import_module_depth,
    ):
        result = (
            rule.invoke(
                cast(
                    "Mapping[type[Fact], Table[Fact]]",
                    {ImportBindingFact: table, ExportFact: exports},
                ),
                settings={},
                dependencies={},
            )
            if rule is import_module_depth
            else rule.invoke_table(table, settings={}, dependencies={})
        )
        if not isinstance(result, RuleQuery):
            raise TypeError("a deterministic import rule returned a model query")
        queries[rule.qualname] = result
    return queries


def test_project_owned_import_queries_keep_values_and_safe_fixes(tmp_path: Path) -> None:
    package = tmp_path / "acme"
    package.mkdir()
    for name, source in {
        "__init__.py": "",
        "models.py": "class User:\n    pass\n",
        "_engine.py": "def execute():\n    pass\n",
        "service.py": """from acme.models import User
from acme._engine import execute

def build():
    return User(), execute()
""",
    }.items():
        (package / name).write_text(source, encoding="utf-8")
    queries = import_queries(tmp_path)

    relative, private = (
        queries[internal_relative_import.qualname],
        queries[project_private_import.qualname],
    )
    assert relative.fix is not None
    assert (
        relative.values.collect().get_column("boolean_value").sum(),
        set(relative.fix.rewrites.collect().get_column("source")),
        private.values.collect().get_column("boolean_value").sum(),
    ) == (2, {".models", "._engine"}, 1)


def test_unused_import_query_keeps_exemptions_and_review_fix(tmp_path: Path) -> None:
    (tmp_path / "subject.py").write_text(
        """from __future__ import annotations
import json
import os
from math import *

value = os.getcwd()
""",
        encoding="utf-8",
    )
    result = import_queries(tmp_path)[unused_import.qualname]
    values = result.values.collect()
    assert result.findings is not None
    findings = result.findings.rows.collect()
    assert result.fix is not None
    assert (
        values.get_column("boolean_value").sum(),
        findings.height,
        "`json` is imported from `json`" in findings.item(0, "message"),
        unused_import.query_fix_safety,
        result.fix.rewrites.collect().get_column("kind").to_list(),
    ) == (1, 1, True, FixSafety.REVIEW, ["remove"])


def test_unused_import_query_addresses_one_binding_in_a_group(tmp_path: Path) -> None:
    """A grouped import offers an exact binding deletion rather than dropping live siblings."""
    (tmp_path / "subject.py").write_text(
        "import json, os\n\nvalue = os.getcwd()\n",
        encoding="utf-8",
    )

    result = import_queries(tmp_path)[unused_import.qualname]

    assert result.fix is not None
    assert result.fix.nodes.collect().select("kind", "text").row(0) == (
        "sequence-item",
        "json",
    )


def test_empty_directory_and_depth_cases() -> None:
    empty = DirectoryFact(key="directory", span=SourceSpan(path="src/unused"))
    result = retained_query(empty, empty_directories)
    assert result.fix is not None
    assert (
        scalar(result),
        scalar(retained_query(empty.model_copy(update={"entry_count": 1}), empty_directories)),
        scalar(retained_query(empty.model_copy(update={"source_depth": 6}), package_depth)),
        empty_directories.query_fix_safety,
        result.fix.rewrites.collect().item(0, "kind"),
        result.fix.rewrites.collect().item(0, "source"),
    ) == (True, False, 6, FixSafety.SAFE, "remove-directory", "src/unused")
    framework = empty.model_copy(update={"span": SourceSpan(path="src/rules/catalog")})
    assert (
        retained_query(
            framework,
            package_depth,
            framework_roots=["src/rules"],
        )
        .values.collect()
        .is_empty()
    )


def test_directory_module_count_cases() -> None:
    """Definition catalogs may opt out of the ordinary direct-module ceiling."""
    crowded = DirectoryFact(
        key="directory",
        span=SourceSpan(path="src/catalog"),
        direct_module_count=7,
    )
    catalog = crowded.model_copy(update={"is_definition_catalog": True})
    assert (
        scalar(retained_query(crowded, directory_module_count)),
        scalar(retained_query(catalog, directory_module_count)),
        scalar(
            retained_query(
                catalog,
                directory_module_count,
                allow_definition_catalogs=True,
            )
        ),
    ) == (7, 7, 0)


def test_directory_pathway_cases() -> None:
    """A real lane and a directory with its own file are not navigation-only pathways."""
    pathway = DirectoryFact(
        key="directory",
        span=SourceSpan(path="src/services"),
        source_depth=2,
        direct_directory_count=1,
        only_child_directory="payments",
    )
    lane = pathway.model_copy(
        update={
            "span": SourceSpan(path="src/rules/python"),
            "only_child_directory": "deterministic",
        }
    )
    assert (
        scalar(retained_query(pathway, directory_pathway)),
        scalar(
            retained_query(
                pathway.model_copy(update={"direct_file_count": 1}),
                directory_pathway,
            )
        ),
        scalar(retained_query(lane, directory_pathway)),
    ) == (True, False, False)


def test_import_depth_counts_named_components_without_relative_dots(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "module.py").write_text(
        """from library.internal.transport.http import Client
from ...transport.http import Relative
""",
        encoding="utf-8",
    )

    result = import_queries(tmp_path)[import_module_depth.qualname]

    assert result.values.collect().get_column("integer_value").to_list() == [4, 2]


def test_deep_import_reuses_one_proven_public_facade(tmp_path: Path) -> None:
    """The depth rule fixes only a complete import with an existing cycle-safe public route."""
    library = tmp_path / "library"
    implementation = library / "internal" / "transport"
    implementation.mkdir(parents=True)
    (library / "__init__.py").write_text(
        'from .internal.transport.http import Client\n\n__all__ = ["Client"]\n'
    )
    (implementation / "http.py").write_text("class Client:\n    pass\n")
    (tmp_path / "consumer.py").write_text(
        "from library.internal.transport.http import Client\n\nclient = Client()\n"
    )
    session = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[ImportBindingFact.__name__, ExportFact.__name__],
    )
    imports = session.import_binding_tables()
    exports = session.table(ExportFact)

    result = import_module_depth.invoke(
        cast(
            "Mapping[type[Fact], Table[Fact]]",
            {ImportBindingFact: imports, ExportFact: exports},
        ),
        settings={},
        dependencies={},
    )

    assert isinstance(result, RuleQuery) and result.fix is not None
    assert result.values.collect().get_column("integer_value").max() == 4
    assert result.fix.rewrites.collect().select("kind", "source").rows() == [
        ("replace", "library")
    ]


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
    assert scalar(retained_query(module, module_line_count)) == 401
    assert scalar(retained_query(module, module_statement_count)) == 201
    assert scalar(retained_query(module, module_class_count)) == 9
    assert scalar(retained_query(module, module_member_count)) == 13
    assert scalar(retained_query(module, non_init_reexport_module)) == 1
    initializer = module.model_copy(update={"is_package_initializer": True})
    assert scalar(retained_query(initializer, non_init_reexport_module)) == 0
    test_module = module.model_copy(update={"span": SourceSpan(path="tests/conftest.py")})
    assert scalar(retained_query(test_module, non_init_reexport_module)) == 0


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
    families = [
        ModuleFact.__name__,
        FunctionFact.__name__,
        CallFact.__name__,
        ClassFact.__name__,
        ImportBindingFact.__name__,
    ]
    session = AnalysisSession(tmp_path, suffixes=[".py"], typed_families=families)
    tables = {
        ModuleFact: session.table(ModuleFact),
        FunctionFact: session.function_tables(),
        CallFact: session.call_tables(),
        ClassFact: session.class_tables(),
        ImportBindingFact: session.import_binding_tables(),
    }

    result = cast(
        "RuleQuery",
        initializer_declaration.invoke(
            cast("Mapping[type[Fact], Table[Fact]]", tables),
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


def export_subject() -> ExportFact:
    """Build one public export with a cycle-safe internal bypass."""
    return ExportFact(
        key="export:pkg.Engine",
        span=SourceSpan(path="pkg/__init__.py"),
        public_export=PublicExport(
            name="Engine",
            target="pkg.engine.Engine",
            nodes=[
                NodeRef(
                    id="pkg/__init__.py:11:sequence-item",
                    span=SourceSpan(
                        path="pkg/__init__.py",
                        start_line=1,
                        start_column=11,
                        end_line=1,
                        end_column=19,
                    ),
                    kind="sequence-item",
                    text='"Engine"',
                )
            ],
            span=SourceSpan(path="pkg/__init__.py"),
        ),
        bypasses=[
            ExportBypass(
                public_module="pkg",
                name="Engine",
                target="pkg.engine.Engine",
                expression="pkg.engine.Engine",
                module_node=NodeRef(
                    id="service.py:5:module",
                    span=SourceSpan(
                        path="service.py",
                        start_line=3,
                        start_column=5,
                        end_line=3,
                        end_column=15,
                    ),
                    kind="module",
                    text="pkg.engine",
                ),
                replacement_module="pkg",
                is_cycle_safe=True,
                span=SourceSpan(path="service.py", start_line=3),
            )
        ],
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
