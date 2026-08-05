from typing import TYPE_CHECKING

from mcmr import Numeric
from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    AttributeAccess,
    AttributeAccessFact,
    ConstantPlacement,
    ExceptionFact,
    ExceptionHandler,
    ExceptionRegion,
    ExceptionUsage,
    ImportBindingFact,
    ModuleFact,
    NodeRef,
    ReceiverKind,
    RuntimeTypeCheck,
    RuntimeTypeCheckFact,
    SourceSpan,
    Symbol,
    SymbolFact,
    SymbolRef,
    TryBlockFact,
    Visibility,
)
from mcmr.plugins import Fact, Table
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import (
    external_nonpublic_attribute_access_count,
)
from mcmr.rules.python import (
    boolean_predicate_name,
    bounded_exception_region,
    broad_try_literal_setup,
    concrete_isinstance_capability,
    cross_module_project_constant_import,
    dependency_safe_constant_order,
    nullable_exception_return_suppression,
    public_module_constant,
    shared_exception_placement,
)
from mcmr.table import AnalysisSession

from ..support import retained_query as query

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_SPAN = SourceSpan(path="src/example.py")


def value(subject: Fact, rule: RuleContract, **settings: RuleSetting) -> RuleValue:
    """Return one scalar from the retained rule query."""
    return scalar_frame_value(query(subject, rule, **settings).values.collect())


def native_query[Family: Fact](
    subject: Table[Family],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one specialized rule once over its complete native table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic native rule returned a model query")
    return result


def symbols(*declared: Symbol) -> SymbolFact:
    """Return one fact holding the given symbols declared by the example module."""
    return SymbolFact(key="symbols", span=_SPAN, symbols=list(declared))


def access(name: str, receiver: ReceiverKind, **declared: bool | Visibility) -> AttributeAccess:
    """Return one attribute read through the given receiver, with what is known of the name."""
    return AttributeAccess.model_validate(
        {
            "name": name,
            "receiver_kind": receiver,
            "node": NodeRef(id=f"{receiver.value}:{name}", span=_SPAN),
        }
        | declared
    )


def usage(*, name: str, module: str, importers: Sequence[str] = ()) -> ExceptionUsage:
    """Return one project exception and the ordinary modules importing it by name."""
    return ExceptionUsage(name=name, defining_module=module, importing_modules=list(importers))


def imported_constant_count(root: Path) -> int:
    """Measure project constant imports in one minimal package."""
    package = root / "project"
    package.mkdir()
    for name, source in {
        "__init__.py": "",
        "settings.py": "TIMEOUT = 30\n",
        "service.py": "from project.settings import TIMEOUT\n\nvalue = TIMEOUT\n",
    }.items():
        (package / name).write_text(source, encoding="utf-8")
    imports = AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[ImportBindingFact],
    ).import_binding_tables()
    return (
        native_query(imports, cross_module_project_constant_import)
        .values.collect()
        .item(0, "boolean_value")
    )


def test_constant_cases(tmp_path: Path) -> None:
    declared = symbols(
        Symbol(name="TIMEOUT", scope="module", is_constant_assignment=True),
        Symbol(name="_PRIVATE", scope="module", is_constant_assignment=True),
        Symbol(name="VALUE", scope="local", is_constant_assignment=True),
    )
    assert value(declared, public_module_constant) == 1

    assert imported_constant_count(tmp_path) == 1

    module = ModuleFact(
        key="module",
        span=_SPAN,
        constant_placements=[
            ConstantPlacement(name="EARLY", intervening_statement_count=0),
            ConstantPlacement(name="LATE", intervening_statement_count=2),
        ],
    )
    assert (
        value(module, dependency_safe_constant_order),
        value(module.model_copy(update={"is_test": True}), dependency_safe_constant_order),
    ) == (1, 0)


def test_a_boolean_name_is_reported_and_renamed_only_where_every_reference_was_found() -> None:
    """A name the file cannot see all of is left alone, and underscores are kept.

    One bare `ready` beside an `is_ready` is enough to report, and the rename that follows moves
    a declaration together with every reference to it.
    """
    subject = symbols(
        Symbol(name="is_ready", scope="class", returns_boolean=True),
        Symbol(name="ready", scope="class", returns_boolean=True),
        Symbol(name="count", scope="class", returns_boolean=False),
    )
    predicates = subject.model_copy(update={"symbols": subject.symbols[:1]})
    assert (
        value(subject, boolean_predicate_name),
        value(predicates, boolean_predicate_name),
    ) == (True, False)

    declaration = NodeRef(id="declaration", span=_SPAN, text="_ready")
    private = Symbol(
        name="_ready",
        scope="module",
        returns_boolean=True,
        reference=SymbolRef(
            id="private.py:_ready",
            name="_ready",
            declaration=declaration,
            references=[NodeRef(id="use", span=_SPAN, text="_ready")],
            are_references_complete=True,
        ),
    )
    exported = private.model_copy(
        update={
            "name": "ready",
            "reference": SymbolRef(id="exported.py:ready", name="ready", declaration=declaration),
        }
    )

    result = query(symbols(private, exported), boolean_predicate_name)
    assert result.fix is not None
    rewrites = result.fix.rewrites.collect()
    assert (rewrites.get_column("name").to_list(), result.fix.nodes.collect().height) == (
        ["_is_ready"],
        2,
    )


def test_runtime_capability_cases() -> None:
    subject = RuntimeTypeCheckFact(
        key="checks",
        span=_SPAN,
        checks=[
            RuntimeTypeCheck(concrete_type="list", guarded_operations=["iterate"]),
            RuntimeTypeCheck(concrete_type="Path", guarded_operations=["read_text"]),
        ],
    )
    single = subject.model_copy(update={"checks": subject.checks[1:]})
    assert value(subject, concrete_isinstance_capability) is True
    assert value(single, concrete_isinstance_capability) is False


def test_nonpublic_attribute_access_cases() -> None:
    subject = AttributeAccessFact(
        key="accesses",
        span=_SPAN,
        accesses=[
            access("_token", ReceiverKind.OTHER, visibility=Visibility.PROTECTED),
            access(
                "_token",
                ReceiverKind.SELF,
                visibility=Visibility.PROTECTED,
                is_inside_owning_class=True,
            ),
            access("__module__", ReceiverKind.OTHER, is_protocol_name=True),
        ],
    )
    assert value(subject, external_nonpublic_attribute_access_count) == 1
    allowed = subject.model_copy(
        update={"accesses": [subject.accesses[0].model_copy(update={"receiver_text": "sys"})]}
    )
    assert (
        value(
            allowed,
            external_nonpublic_attribute_access_count,
            allowed=["sys._token"],
        )
        == 0
    )


def test_exception_region_cases() -> None:
    """One project answers how wide its protected exception regions are."""
    regions = TryBlockFact(
        key="try blocks",
        span=_SPAN,
        regions=[
            ExceptionRegion(
                leading_literal_assignment_count=2,
                has_following_raising_operation=True,
                clause_statement_counts=[3, 1],
            ),
            ExceptionRegion(
                leading_literal_assignment_count=1,
                has_following_raising_operation=False,
                clause_statement_counts=[2],
            ),
        ],
    )
    assert value(regions, broad_try_literal_setup) == 1
    assert value(regions, bounded_exception_region) == 3
    assert value(regions.model_copy(update={"regions": []}), bounded_exception_region) == 0
    assert bounded_exception_region.policy == Numeric(maximum=1)


def test_nullable_exception_return_has_one_safe_suppression_rewrite() -> None:
    """Only the exact one-return control flow becomes a suppress block."""
    statement = NodeRef(
        id="try",
        span=_SPAN,
        kind="try",
        text="try:\n    return validate(value)\nexcept ValidationError:\n    return None",
    )
    protected = NodeRef(
        id="protected",
        span=_SPAN,
        kind="return",
        text="return validate(value)",
    )
    fallback = NodeRef(id="fallback", span=_SPAN, kind="return", text="return None")
    region = ExceptionRegion(
        statement=statement,
        protected_statements=[protected],
        handlers=[
            ExceptionHandler(caught="ValidationError", body=[fallback]),
        ],
    )
    result = query(
        TryBlockFact(key="try blocks", span=_SPAN, regions=[region]),
        nullable_exception_return_suppression,
    )

    assert result.fix is not None
    aliased = region.model_copy(
        update={"handlers": [region.handlers[0].model_copy(update={"alias": "error"})]}
    )
    assert (
        result.values.collect().item(0, "integer_value"),
        result.fix.rewrites.collect().item(0, "source"),
        result.fix.imports.collect().select("module", "name").row(0),
        value(
            TryBlockFact(key="try blocks", span=_SPAN, regions=[aliased]),
            nullable_exception_return_suppression,
        ),
    ) == (
        1,
        "with suppress(ValidationError):\n    return validate(value)\nreturn None",
        ("contextlib", "suppress"),
        0,
    )


def test_shared_exception_placement_cases() -> None:
    """Shared exception types live where every importing module can depend on them."""
    usages = ExceptionFact(
        key="exceptions",
        span=_SPAN,
        exceptions=[
            usage(
                name="ConfigurationError",
                module="project.config",
                importers=["project.cli", "project.api"],
            ),
            usage(
                name="LocalError",
                module="project.local",
                importers=["project.local.worker"],
            ),
            usage(
                name="SharedError",
                module="project.exceptions",
                importers=["project.cli", "project.api"],
            ),
        ],
    )
    assert value(usages, shared_exception_placement) == 1
    assert value(usages, shared_exception_placement, minimum_importing_modules=3) == 0
