import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from patos import FrozenModel

from mcmr.domain.contracts import Unit
from mcmr.facts import (
    CallFact,
    ClassFact,
    FunctionFact,
    ImportBindingFact,
    SyntaxFact,
)
from mcmr.query import RuleQuery
from mcmr.table import Table, fact_table

from ...support import FactValue, built_catalog, family_of

if TYPE_CHECKING:
    from mcmr.domain.contracts import RuleContract, RuleDefinition, RuleValue
    from mcmr.facts import Fact


_SPECIALIZED_FAMILIES: set[type[Fact]] = {
    CallFact,
    ClassFact,
    FunctionFact,
    ImportBindingFact,
    SyntaxFact,
}


def readable() -> dict[type[Fact], list[tuple[RuleContract, RuleDefinition]]]:
    """Group generic retained-table rules by the fact family they declare.

    The model lanes are left out because a judgment needs a backend to reach, and a rule asking for
    an explicit dependency is left out for the same reason. Specialized graph families are covered
    by their native columnar suites and repository fixtures because arbitrary Pydantic objects
    cannot state their relational invariants.
    """
    catalog = built_catalog()
    by_path = {rule.callable_path: rule for rule in catalog.rules}
    grouped: dict[type[Fact], list[tuple[RuleContract, RuleDefinition]]] = {}
    for definition in catalog.definitions:
        rule = by_path[definition.callable]
        family = family_of(rule)
        if (
            definition.lane != "deterministic"
            or rule.injected
            or len(rule.tables) != 1
            or family in _SPECIALIZED_FAMILIES
        ):
            continue
        grouped.setdefault(family, []).append((rule, definition))
    return grouped


_READERS = readable()
_FAMILIES = sorted(_READERS, key=lambda family: family.__name__)

# Rules that read a meaningful stream position are listed with the reason. Every other rule must
# ignore provider discovery order because nothing promises one.
_ORDERED: dict[str, str] = {
    "ALL-CLAS0001": (
        "the methods a class declares are ordered by source, which is the exact order this rule "
        "compares with the configured member order"
    ),
    "ALL-CLAS0005": (
        "the bases a class declares are ordered by the language rather than by the kernel, so "
        "this rule counts the chain at the first base and stays quiet at every other one"
    ),
    "ALL-OVER0007": (
        "it reads the first declared base for the same reason, so one initializer is judged once "
        "rather than once per base the class happens to name"
    ),
    "ALL-OVER0002": (
        "positional parameters bind in source order, so this rule compares the name occupying "
        "each caller-visible position"
    ),
    "ALL-OVER0003": (
        "the receiver is the first classmethod parameter in source order, and the descriptor "
        "supplies that position rather than exposing it to a caller"
    ),
}


def reversed_records[Record: FrozenModel](record: Record) -> Record:
    """Return the same record with every list beneath it stated in the opposite order.

    Reversing only the streams a fact holds directly leaves most of the catalog untouched, since a
    class is a record holding members and a declaration is a node holding nodes. Going all the way
    down is what puts the rules that read a position under the same claim as the rest.
    """
    model: type[Record] = type(record)
    return model.model_validate(
        {name: turned(getattr(record, name)) for name in model.model_fields}
    )


def turned(value: FactValue) -> FactValue:
    """Return one field value with every list beneath it stated in the opposite order."""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [turned(item) for item in reversed(value)]
    if isinstance(value, FrozenModel):
        return reversed_records(value)
    return value


def is_inside(value: RuleValue, definition: RuleDefinition) -> bool:
    """Whether one answer sits inside the domain its rule's declared output states."""
    match definition.output:
        case "bool":
            return isinstance(value, bool)
        case "int":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 0
        case "float":
            return isinstance(value, float) and math.isfinite(value) and 0.0 <= value <= 100.0
        case "category":
            return isinstance(value, str) and value in definition.categories
        case _:
            return False


def retained(subject: Fact) -> Table[Fact]:
    """Normalize one arbitrary generic fact through the native in-memory table boundary."""
    return fact_table(type(subject), [subject])


def queried(rule: RuleContract, table: Table[Fact]) -> RuleQuery:
    """Execute one deterministic rule once over a normalized fact table."""
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError(f"{rule.callable_path} returned a contextual model query")
    return result


def assert_table_findings(outcome: RuleQuery, definition: RuleDefinition) -> None:
    """Require one table answer, its findings, and its declared fix to agree."""
    value = scalar(outcome)
    assert outcome.findings is not None, definition.id
    findings = list(outcome.findings.normalized().rows.collect().iter_rows(named=True))
    default = any(fix.is_default for fix in definition.fixes)

    if isinstance(value, bool):
        assert bool(findings) is value, (
            f"{definition.id} answered {value!r} beside {len(findings)} findings"
        )
    elif isinstance(value, int | float) and value != 0:
        assert findings, f"{definition.id} answered {value!r} without a finding"
    for finding in findings:
        assert finding["message"].strip(), f"{definition.id} stated a finding saying nothing"
        for name, measurement, unit in zip(
            finding["measurement_names"],
            finding["measurement_values"],
            finding["measurement_units"],
            strict=True,
        ):
            scaled = unit != str(Unit.PERCENTAGE) or 0.0 <= measurement <= 100.0
            assert math.isfinite(measurement), f"{definition.id} measured {name} as {measurement}"
            assert scaled, f"{definition.id} measured {name} outside a percentage"
    assert (outcome.fix is not None) is default, (
        f"{definition.id} table fix and catalog default disagree"
    )


def scalar(query: RuleQuery) -> RuleValue:
    """Return the populated scalar from a one-row rule query."""
    values = query.values.collect()
    assert values.height == 1
    row = values.row(0, named=True)
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        if (value := row[name]) is not None:
            return cast("RuleValue", value)
    raise TypeError("the rule emitted no scalar value")


def families() -> list[type[Fact]]:
    """Return generic families covered by the property sweep."""
    return _FAMILIES


def ordered() -> dict[str, str]:
    """Return rules whose source order is part of their contract."""
    return _ORDERED


def readers() -> dict[type[Fact], list[tuple[RuleContract, RuleDefinition]]]:
    """Return deterministic generic rules grouped by their family."""
    return _READERS


def specialized_families() -> set[type[Fact]]:
    """Return families verified through dedicated native tables."""
    return _SPECIALIZED_FAMILIES
