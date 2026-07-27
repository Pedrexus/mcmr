from typing import get_args, get_origin

from mcmr.bases import FrozenFlexModel
from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import Fact, NodeRef, Relation, SourceSpan, SymbolRef
from mcmr.kernel import VENDORED, Kernel, buildable
from tests.conftest import BINARY, ROOT, needs_kernel

# How far into a fact this reads, matching `tests/test_fact_variation.py`. A fact holds one list of
# records and each record holds its own, and below that the shapes are addressing plumbing rather
# than evidence a rule judges.
DEPTH = 2

# Where a fact is rather than what it says, which is never the evidence a rule reasons over.
ADDRESS = (NodeRef, SourceSpan, SymbolRef)

# The vocabulary a rule uses to say it needs records drawn from more than one file. It is a setting
# the rule declares in its own signature, which is what makes this check mechanical rather than a
# reading of prose, and the catalog already refuses a setting that does not affect a rule.
FLOOR = "files"

# Rules that ask for evidence their fact family cannot hold, with what each one needs. This is the
# defect `ALL-ARCH0011` had and it is the reason this file exists. A rule asking for a value
# repeated across two files while reading a family built one file at a time answers zero forever
# and reads exactly like a clean repository, so it has to be recorded here or fail the suite. The
# ledger fails in both directions, so an entry left behind after a family widens fails it too.
UNSATISFIABLE: dict[str, str] = {
    "ALL-DEPE0010": (
        "`CallFact` is one fact per file and every call in it carries that same path, so grouping "
        "one external callable across two files can never reach the floor. It needs the calls "
        "grouped by qualified name across the repository. Six of the flags it also reads are in "
        "the variation ledger as fields no frontend writes, so this rule is dead twice over"
    ),
    "ALL-DUPL0002": (
        "the string groups of `LiteralGroupFact` are built one file at a time, so a group carries "
        "one path and the two-file floor is never met. It needs the groups joined across the "
        "repository the way the module import graph now is, which also means splitting the enum "
        "metadata maps out, since those are a question about one file"
    ),
    "PY-TYPE0007": (
        "`TypeAnnotationFact` is one fact per file and every annotation in it carries that same "
        "path, so counting distinct paths can only ever reach one. It needs the constrained "
        "annotation recipes joined across the repository as their own family, since making the "
        "whole annotation family repository-wide would take every other rule reading it with it"
    ),
}


def held(annotation: type | None) -> type[FrozenFlexModel] | None:
    """Return the model one annotation carries, looking through a list and through a union."""
    if isinstance(annotation, type):
        return annotation if issubclass(annotation, FrozenFlexModel) else None
    return next(
        (found for argument in get_args(annotation) if (found := held(argument)) is not None),
        None,
    )


def sequence(annotation: type | None) -> bool:
    """Whether one annotation carries a list of models rather than one model."""
    return get_origin(annotation) is list or any(
        sequence(argument) for argument in get_args(annotation)
    )


def relations(prefix: str, model: type[FrozenFlexModel], depth: int) -> list[str]:
    """Return every path at which one family carries a relation between two named units."""
    found: list[str] = []
    for name, field in model.model_fields.items():
        inner = held(field.annotation)
        if inner is None or issubclass(inner, ADDRESS):
            continue
        path = f"{prefix}.{name}[]" if sequence(field.annotation) else f"{prefix}.{name}"
        found += [path] if issubclass(inner, Relation) else []
        found += relations(path, inner, depth + 1) if depth < DEPTH else []
    return found


def columns(prefix: str, model: FrozenFlexModel, seen: dict[str, set[str]], depth: int) -> None:
    """Record what each end of every relation one fact holds was named, one record at a time."""
    if isinstance(model, Relation):
        seen.setdefault(f"{prefix}.source", set()).add(model.source)
        seen.setdefault(f"{prefix}.target", set()).add(model.target)
    for name, field in type(model).model_fields.items():
        inner = held(field.annotation)
        value = getattr(model, name)
        if inner is None or issubclass(inner, ADDRESS) or depth >= DEPTH or not value:
            continue
        path = f"{prefix}.{name}[]" if isinstance(value, list) else f"{prefix}.{name}"
        for item in value if isinstance(value, list) else [value]:
            columns(path, item, seen, depth + 1)


def strings(model: FrozenFlexModel, depth: int) -> set[str]:
    """Return every plain string one fact states, down to the depth a rule reads."""
    found: set[str] = set()
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        inner = held(field.annotation)
        if inner is None:
            found |= {
                item
                for item in (value if isinstance(value, list) else [value])
                if isinstance(item, str)
            }
            continue
        if issubclass(inner, ADDRESS) or depth >= DEPTH or not value:
            continue
        for item in value if isinstance(value, list) else [value]:
            found |= strings(item, depth + 1)
    return found


def sited(fact: Fact) -> set[str]:
    """Return how many of this repository's files one fact names anywhere in its records.

    Which strings are paths is settled by asking the filesystem rather than by trusting a field
    name, so a family carrying its locations under any spelling is read the same way.
    """
    return {value for value in strings(fact, 0) if (ROOT / value).is_file()}


def built(families: dict[str, type[Fact]]) -> dict[str, list[Fact]]:
    """Build exactly these families over this repository, which is the corpus for both checks."""
    workspace = Kernel(binary=BINARY, root=ROOT, exclude=VENDORED).build(
        sorted(families), families
    )
    return {name: workspace.stream(family) for name, family in families.items()}


def floors() -> dict[str, tuple[str, int]]:
    """Return, for every rule declaring a floor on distinct files, the family it reads."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    return {
        definition.id: (definition.fact, int(value))
        for definition in catalog.definitions
        for name, value in definition.settings.items()
        if FLOOR in name and value.isdigit() and int(value) > 1
    }


@needs_kernel
def test_no_relation_states_its_two_ends_in_a_vocabulary_of_its_own() -> None:
    """A relation whose columns never meet is a graph with no path, and answers zero forever.

    This is the exact shape `ALL-ARCH0011` had. Its edges were spelled `flask.app.py` on one side
    and `collections.abc` on the other, so no two of them ever joined, no component could form,
    and the rule reported a clean repository for every repository there is. Nothing in the suite
    could see it, because the field did vary. It varied over the wrong vocabulary.

    A relation between two different kinds of thing, such as a test naming the module it exercises,
    is not one of these and should not be typed as one, since its columns are two vocabularies on
    purpose rather than by accident.
    """
    families = buildable()
    carried = {
        name: paths for name, family in families.items() if (paths := relations(name, family, 0))
    }

    assert carried, "no family carries a relation, so this check has stopped checking anything"
    seen: dict[str, set[str]] = {}
    for name, facts in built({name: families[name] for name in carried}).items():
        for fact in facts:
            columns(name, fact, seen, 0)
    for paths in carried.values():
        for path in paths:
            assert seen.get(f"{path}.source", set()) & seen.get(f"{path}.target", set()), path


@needs_kernel
def test_a_rule_needing_records_from_several_files_reads_a_family_that_holds_them() -> None:
    """A per-file fact cannot answer a question about two files, however the rule is written.

    The rule states its own requirement, since a floor on distinct files is a setting in its
    signature rather than a claim in its prose. What the family can hold is read off the corpus by
    counting the files any one fact names, so neither half of the comparison is a declaration
    somebody has to keep true by hand.
    """
    demanded = floors()

    assert demanded, "no rule declares a file floor, so this check has stopped checking anything"
    facts = built(
        {family: buildable()[family] for family, _ in demanded.values() if family in buildable()}
    )
    widest = {
        family: max((len(sited(fact)) for fact in stream), default=0)
        for family, stream in facts.items()
    }
    unsatisfiable = {
        rule for rule, (family, floor) in demanded.items() if widest.get(family, 0) < floor
    }

    assert sorted(unsatisfiable - set(UNSATISFIABLE)) == []
    assert sorted(set(UNSATISFIABLE) - unsatisfiable) == []
    assert all(reason for reason in UNSATISFIABLE.values())
