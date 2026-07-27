from mcmr.facts import (
    AttributeAccess,
    AttributeAccessFact,
    ConstantPlacement,
    ExceptionFact,
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
from mcmr.models import Rename
from mcmr.rules.general.deterministic.encapsulation.r0001 import (
    external_nonpublic_attribute_access_count,
)
from mcmr.rules.python.deterministic.constants.r0001 import public_module_constant
from mcmr.rules.python.deterministic.constants.r0002 import (
    cross_module_project_constant_import,
)
from mcmr.rules.python.deterministic.constants.r0003 import dependency_safe_constant_order
from mcmr.rules.python.deterministic.exceptions.r0001 import broad_try_literal_setup
from mcmr.rules.python.deterministic.exceptions.r0002 import bounded_exception_region
from mcmr.rules.python.deterministic.exceptions.r0003 import shared_exception_placement
from mcmr.rules.python.deterministic.interfaces.r0001 import concrete_isinstance_capability
from mcmr.rules.python.deterministic.naming.r0002 import (
    boolean_predicate_name,
    rename_boolean_symbol,
)

SPAN = SourceSpan(path="src/example.py")


def symbols(*declared: Symbol) -> SymbolFact:
    """Return one fact holding the given symbols declared by the example module."""
    return SymbolFact(key="symbols", span=SPAN, symbols=list(declared))


def access(name: str, receiver: ReceiverKind, **declared: bool | Visibility) -> AttributeAccess:
    """Return one attribute read through the given receiver, with what is known of the name."""
    return AttributeAccess.model_validate({"name": name, "receiver_kind": receiver} | declared)


def usage(name: str, module: str, *importers: str) -> ExceptionUsage:
    """Return one project exception and the ordinary modules importing it by name."""
    return ExceptionUsage(name=name, defining_module=module, importing_modules=list(importers))


def test_constant_cases() -> None:
    declared = symbols(
        Symbol(name="TIMEOUT", scope="module", is_constant_assignment=True),
        Symbol(name="_PRIVATE", scope="module", is_constant_assignment=True),
        Symbol(name="VALUE", scope="local", is_constant_assignment=True),
    )
    assert public_module_constant(declared) == 1

    imported = ImportBindingFact(
        key="import",
        span=SPAN,
        name="TIMEOUT",
        imported_name="TIMEOUT",
        module="project.settings",
        is_project_owned=True,
    )
    external = imported.model_copy(update={"is_project_owned": False})
    assert cross_module_project_constant_import(imported) == 1
    assert cross_module_project_constant_import(external) == 0

    module = ModuleFact(
        key="module",
        span=SPAN,
        constant_placements=[
            ConstantPlacement(name="EARLY", intervening_statement_count=0),
            ConstantPlacement(name="LATE", intervening_statement_count=2),
        ],
    )
    assert dependency_safe_constant_order(module) == 1


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
    assert boolean_predicate_name(subject).value
    assert not boolean_predicate_name(predicates).value

    declaration = NodeRef(id="declaration", span=SPAN, text="_ready")
    private = Symbol(
        name="_ready",
        scope="module",
        returns_boolean=True,
        reference=SymbolRef(
            id="private.py:_ready",
            name="_ready",
            declaration=declaration,
            references=[NodeRef(id="use", span=SPAN, text="_ready")],
            are_references_complete=True,
        ),
    )
    exported = private.model_copy(
        update={
            "name": "ready",
            "reference": SymbolRef(id="exported.py:ready", name="ready", declaration=declaration),
        }
    )

    plan = rename_boolean_symbol(symbols(private, exported))
    assert plan is not None
    renamed = [rewrite.name for rewrite in plan.rewrites if isinstance(rewrite, Rename)]
    assert renamed == ["_is_ready"]
    assert len(plan.rewrites[0].spans) == 2


def test_runtime_capability_cases() -> None:
    subject = RuntimeTypeCheckFact(
        key="checks",
        span=SPAN,
        checks=[
            RuntimeTypeCheck(concrete_type="list", guarded_operations=["iterate"]),
            RuntimeTypeCheck(concrete_type="Path", guarded_operations=["read_text"]),
        ],
    )
    single = subject.model_copy(update={"checks": subject.checks[1:]})
    assert concrete_isinstance_capability(subject)
    assert not concrete_isinstance_capability(single)


def test_nonpublic_attribute_access_cases() -> None:
    subject = AttributeAccessFact(
        key="accesses",
        span=SPAN,
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
    assert external_nonpublic_attribute_access_count(subject) == 1


def test_exception_region_and_placement_cases() -> None:
    """One project answers how wide its protected regions are and where its shared types live."""
    regions = TryBlockFact(
        key="try blocks",
        span=SPAN,
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
    assert broad_try_literal_setup(regions) == 1
    assert bounded_exception_region(regions) == 3
    assert bounded_exception_region(regions.model_copy(update={"regions": []})) == 0

    usages = ExceptionFact(
        key="exceptions",
        span=SPAN,
        exceptions=[
            usage("ConfigurationError", "project.config", "project.cli", "project.api"),
            usage("LocalError", "project.local", "project.local.worker"),
            usage("SharedError", "project.exceptions", "project.cli", "project.api"),
        ],
    )
    assert shared_exception_placement(usages) == 1
    assert shared_exception_placement(usages, minimum_importing_modules=3) == 0
