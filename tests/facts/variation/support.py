from typing import TYPE_CHECKING, get_args

from patos import FrozenModel

from mcmr.facts import NodeRef, SourceSpan, SymbolRef, buildable
from mcmr.kernel import Kernel
from mcmr.plugins import Fact

from ...support import kernel_binary

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_ADDRESS = (NodeRef, SourceSpan, SymbolRef)
_ENVELOPE = set(Fact.model_fields)
_STATED = "stated"
_ABSENT = "absent"

_UNFILLED: dict[str, str] = {
    "KernelLaunchFact": ("only a CUDA source states a launch and this corpus holds no CUDA"),
    "ModuleSurfaceFact": (
        "only the TypeScript frontend fills it and this corpus holds no TypeScript"
    ),
}

# Every fact field this corpus never moves is paired with the missing shape.

# Provider defaults and literals cannot remain because they make rules unable to fire. The ledger
# turns the next constant field into a test failure instead of a false clean report.
_INVARIANT: dict[str, str] = {
    "AttributeAccessFact.accesses[].receiver_type": (
        "derived, and every statically typed receiver in this corpus names the same local type"
    ),
    "AttributeAccessFact.accesses[].receiver_type_bases": (
        "derived, and no statically typed receiver in this corpus inherits another local type"
    ),
    "CallFact.calls[].receiver.recursive.entries[].recursive.key": (
        "derived, and no nested mapping expression in the corpus states a keyed entry"
    ),
    "CallFact.calls[].has_ambiguous_alias": (
        "derived, and no scope in the corpus binds one name through two imports"
    ),
    "ClassFact.classes[].duplicate_component_alias_count": (
        "derived, and no constructor in the corpus copies a field off a component it also keeps"
    ),
    "ClassFact.classes[].has_noncooperative_concrete_collision": (
        "derived, and no class in the corpus takes one concrete member from two direct bases"
    ),
    "ClassFact.classes[].has_redundant_direct_base": (
        "derived, and no class in the corpus names a base one of its other bases already inherits"
    ),
    "ClassFact.coupled_groups[].type_count": (
        "derived, and every short co-imported role group in the corpus contains two types"
    ),
    "ClassFact.coupled_groups[].coimporting_module_count": (
        "derived, and every coupled type group in the corpus is imported by one module"
    ),
    "ClassFact.coupled_groups[].maximum_type_lines": (
        "derived, and every coupled type group in the corpus has the same largest declaration"
    ),
    "ClassFact.coupled_groups[].prefix": (
        "derived, and the corpus contains one coupled type naming family"
    ),
    "ClassFact.coupled_groups[].role_suffixes": (
        "derived, and the corpus contains one coupled type role combination"
    ),
    "CloneGroupFact.repository_line_count": (
        "one number per repository, and only this repository states a clone group at all"
    ),
    "ComprehensionFact.set_loop_candidates": (
        "derived, and no file in the corpus fills a set through a bare loop"
    ),
    "Enum.enums[].overrides_generate_next_value": (
        "derived, and no enumeration in the corpus writes its own value generator"
    ),
    "FunctionFact.created_task_count": (
        "derived, and no callable in the corpus schedules work through the asyncio its own file "
        "imported"
    ),
    "FunctionFact.gather_consumes_created_tasks": (
        "derived, and no callable in the corpus gathers tasks it created itself"
    ),
    "FunctionFact.gather_returns_exceptions": (
        "derived, and no callable in the corpus gathers anything at all"
    ),
    "FunctionFact.has_task_group": (
        "derived, and no callable in the corpus opens an asyncio task group"
    ),
    "FunctionFact.has_tensor_dtype_semantics": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "FunctionFact.has_tensor_shape_semantics": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "FunctionFact.is_overload": (
        "derived, and no Python callable in the corpus wears the overload decorator"
    ),
    "FunctionFact.recognized_tensor_roles": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "ImportBindingFact.has_documented_side_effect": (
        "derived, and no import in the corpus sits under a `try` that handles an import failure"
    ),
    "ImportBindingFact.has_private_module_component": (
        "derived, and no import in the corpus names a private package component"
    ),
    "ImportBindingFact.is_wildcard": ("derived, and no module in the corpus states a star import"),
    "SyntaxFact.tree": (
        "expanded trees exist only in direct rule fixtures, while every provider writes the "
        "compact node stream"
    ),
    "TestFunctionFact.tests[].generated_parametrization_count": (
        "derived, and no parametrized test in the corpus reads cases generated at module scope"
    ),
    "RepositoryHistoryFact.unscoped_commit_count": (
        "derived from the checkout, whose one current commit changed requested source"
    ),
    "RepositoryHistoryFact.files[].author_count": ("derived from the same one-author root commit"),
    "QueryFact.operations[].expire_on_commit": (
        "derived from the keywords a session factory carries, and the one database operation "
        "the corpus states is a commit rather than a factory"
    ),
    "QueryFact.operations[].has_unknown_keywords": (
        "derived from the keywords a session factory carries, and the one database operation "
        "the corpus states carries none"
    ),
    "RouteFact.frameworks": ("derived, and no framework in the corpus declares a route"),
    "RouteFact.routes": ("derived, and no framework in the corpus declares a route"),
    "RustSurfaceFact.annotations[].receiver": (
        "derived, and no lifetime the corpus states appears on a receiver"
    ),
    "TestSuiteFact.asyncio_mode": (
        "derived, and neither manifest in the corpus configures an asyncio mode"
    ),
    "TryBlockFact.regions[].has_following_raising_operation": (
        "derived, and every protected region in the corpus holds more than leading assignments"
    ),
    "TryBlockFact.regions[].has_else": (
        "derived, and no protected region in the corpus states an `else` clause"
    ),
    "TryBlockFact.regions[].is_exception_group": (
        "derived, and no protected region in the corpus uses an exception group handler"
    ),
    "TryBlockFact.regions[].leading_literal_assignment_count": (
        "derived, and no protected region in the corpus opens with a literal assignment"
    ),
    "WaiverFact.waivers[].is_overly_broad": (
        "derived, and every suppression in the corpus names the rule it waives"
    ),
}


def invariant_reasons() -> dict[str, str]:
    """Return reasons that observed fact fields remain invariant."""
    return dict(_INVARIANT)


def unfilled_reasons() -> dict[str, str]:
    """Return reasons that the corpus leaves fact families empty."""
    return dict(_UNFILLED)


def collect(root: Path, seen: dict[str, set[str]]) -> None:
    """Build every family the kernel knows over one root and read what each field held."""
    families = buildable()
    kernel = Kernel(binary=kernel_binary(), root=root)
    workspace = kernel.build(sorted(families), families)
    for name, family in families.items():
        for fact in workspace.stream(family):
            record(name, fact, seen)


def record(prefix: str, model: FrozenModel, seen: dict[str, set[str]]) -> None:
    """Record what one model held, one field at a time through every stated record."""
    record_fields(prefix, model, seen, ancestors={})


def record_fields(
    prefix: str,
    model: FrozenModel,
    seen: dict[str, set[str]],
    *,
    ancestors: dict[type[FrozenModel], str],
) -> None:
    """Aggregate a recursive model under one stable path instead of imposing a depth cap."""
    kind = type(model)
    if kind in ancestors:
        prefix = f"{ancestors[kind]}.recursive"
    else:
        ancestors = ancestors | {kind: prefix}
    for name in type(model).model_fields:
        _record_field(prefix, model, name, seen, ancestors=ancestors)


def _record_field(
    prefix: str,
    model: FrozenModel,
    name: str,
    seen: dict[str, set[str]],
    *,
    ancestors: dict[type[FrozenModel], str],
) -> None:
    """Record one field and descend when it contains another model."""
    if isinstance(model, Fact) and name in _ENVELOPE:
        return
    inner = held(type(model).model_fields[name].annotation)
    if inner is not None and issubclass(inner, _ADDRESS):
        return
    value = getattr(model, name)
    path = f"{prefix}.{name}"
    if inner is None:
        seen.setdefault(path, set()).add(repr(value))
        return
    stated = bool(value) if isinstance(value, list) else value is not None
    seen.setdefault(path, set()).add(_STATED if stated else _ABSENT)
    if not stated:
        return
    for item in value if isinstance(value, list) else [value]:
        record_fields(
            f"{path}[]" if isinstance(value, list) else path,
            item,
            seen,
            ancestors=ancestors,
        )


def unmoved(observed: Mapping[str, set[str]]) -> set[str]:
    """Return every field the corpus never moved, which is the ledger this test holds."""
    return {path for path, values in observed.items() if len(values) == 1 and values != {_STATED}}


def held(annotation: type | None) -> type[FrozenModel] | None:
    """Return the model one annotation carries, looking through a list and through a union."""
    if isinstance(annotation, type):
        return annotation if issubclass(annotation, FrozenModel) else None
    return next(
        (found for argument in get_args(annotation) if (found := held(argument)) is not None),
        None,
    )
