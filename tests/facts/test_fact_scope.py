from typing import TYPE_CHECKING, get_args, get_origin

from patos import FrozenModel

from mcmr.facts import Fact, NodeRef, Relation, SourceSpan, SymbolRef
from mcmr.kernel import Kernel, buildable

from ..support import kernel_binary, needs_kernel, project_root

if TYPE_CHECKING:
    from collections.abc import Sequence

# Where a fact is rather than what it says, which is never the evidence a rule reasons over.
_ADDRESS = (NodeRef, SourceSpan, SymbolRef)


def held(annotation: type | None) -> type[FrozenModel] | None:
    """Return the model one annotation carries, looking through a list and through a union."""
    if isinstance(annotation, type):
        return annotation if issubclass(annotation, FrozenModel) else None
    return next(
        (found for argument in get_args(annotation) if (found := held(argument)) is not None),
        None,
    )


def is_sequence(annotation: type | None) -> bool:
    """Whether one annotation carries a list of models rather than one model."""
    return get_origin(annotation) is list or any(
        is_sequence(argument) for argument in get_args(annotation)
    )


def relations(
    prefix: str,
    model: type[FrozenModel],
    trail: Sequence[type[FrozenModel]] | None = None,
) -> list[str]:
    """Return every relation path, stopping only when a model schema refers to itself."""
    trail = trail or []
    if model in trail:
        return []
    found: list[str] = []
    nested_trail = [*trail, model]
    for name, field in model.model_fields.items():
        inner = held(field.annotation)
        if inner is None or issubclass(inner, _ADDRESS):
            continue
        path = f"{prefix}.{name}[]" if is_sequence(field.annotation) else f"{prefix}.{name}"
        found += [path] if issubclass(inner, Relation) else []
        found += relations(path, inner, nested_trail)
    return found


def columns(prefix: str, model: FrozenModel, seen: dict[str, set[str]]) -> None:
    """Record what each end of every relation one fact holds was named, one record at a time."""
    if isinstance(model, Relation):
        seen.setdefault(f"{prefix}.source", set()).add(model.source)
        seen.setdefault(f"{prefix}.target", set()).add(model.target)
    for name, field in type(model).model_fields.items():
        inner = held(field.annotation)
        value = getattr(model, name)
        if inner is None or issubclass(inner, _ADDRESS) or not value:
            continue
        path = f"{prefix}.{name}[]" if isinstance(value, list) else f"{prefix}.{name}"
        for item in value if isinstance(value, list) else [value]:
            columns(path, item, seen)


def built(families: dict[str, type[Fact]]) -> dict[str, list[Fact]]:
    """Build exactly these families over this repository, which is the corpus for both checks."""
    workspace = Kernel(binary=kernel_binary(), root=project_root()).build(
        sorted(families), families
    )
    return {name: workspace.stream(family) for name, family in families.items()}


@needs_kernel
def test_no_relation_states_its_two_ends_in_a_vocabulary_of_its_own() -> None:
    """A relation whose columns never meet is a graph with no path, and answers zero forever.

    This is the exact shape `ALL-ARCH0002` had. Its edges were spelled `flask.app.py` on one side
    and `collections.abc` on the other, so no two of them ever joined, no component could form,
    and the rule reported a clean repository for every repository there is. Nothing in the suite
    could see it, because the field did vary. It varied over the wrong vocabulary.

    A relation between two different kinds of thing, such as a test naming the module it exercises,
    is not one of these and should not be typed as one, since its columns are two vocabularies on
    purpose rather than by accident.
    """
    families = buildable()
    carried = {
        name: paths for name, family in families.items() if (paths := relations(name, family))
    }

    assert carried, "no family carries a relation, so this check has stopped checking anything"
    seen: dict[str, set[str]] = {}
    for name, facts in built({name: families[name] for name in carried}).items():
        for fact in facts:
            columns(name, fact, seen)
    for paths in carried.values():
        for path in paths:
            assert seen.get(f"{path}.source", set()) & seen.get(f"{path}.target", set()), path
