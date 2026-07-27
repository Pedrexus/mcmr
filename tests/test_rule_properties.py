import math
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from mcmr.bases import FrozenFlexModel
from mcmr.facts import (
    CloneFragment,
    CloneGroupFact,
    ComprehensionFact,
    EscapeHatch,
    ModuleSurfaceFact,
    OverrideFact,
    SourceSpan,
)
from mcmr.models import Unit, answered, explained, reports_findings
from mcmr.rules.general.deterministic.classes.r0009 import ancestor_count
from mcmr.rules.general.deterministic.overrides.r0007 import initializer_called_on_a_stranger
from tests.conftest import FactValue, built_catalog, facts_of, family_of, synchronous

if TYPE_CHECKING:
    from mcmr.facts import Fact
    from mcmr.models import RuleContract, RuleDefinition, RuleValue


def readable() -> dict[type[Fact], list[tuple[RuleContract, RuleDefinition]]]:
    """Group every rule this sweep can invoke by the fact family it declares.

    The model lanes are left out because a judgment needs a backend to reach, and a rule asking for
    an explicit dependency is left out for the same reason. What is left is every rule that reaches
    its answer from one fact alone, which is the whole deterministic catalog.
    """
    catalog = built_catalog()
    by_path = {rule.callable_path: rule for rule in catalog.rules}
    grouped: dict[type[Fact], list[tuple[RuleContract, RuleDefinition]]] = {}
    for definition in catalog.definitions:
        rule = by_path[definition.callable]
        if definition.lane != "deterministic" or rule.injected:
            continue
        grouped.setdefault(family_of(rule), []).append((rule, definition))
    return grouped


READERS = readable()
FAMILIES = sorted(READERS, key=lambda family: family.__name__)

# Which rules read a position in a stream rather than the stream, and why that position is real.
# Everything else has to answer the same thing whatever order a provider discovered its records
# in, since nothing promises one.
ORDERED: dict[str, str] = {
    "ALL-CLAS0009": (
        "the bases a class declares are ordered by the language rather than by the kernel, so "
        "this rule counts the chain at the first base and stays quiet at every other one"
    ),
    "ALL-OVER0007": (
        "it reads the first declared base for the same reason, so one initializer is judged once "
        "rather than once per base the class happens to name"
    ),
}


def reversed_records[Record: FrozenFlexModel](record: Record) -> Record:
    """Return the same record with every list beneath it stated in the opposite order.

    Reversing only the streams a fact holds directly leaves most of the catalog untouched, since a
    class is a record holding members and a declaration is a node holding nodes. Going all the way
    down is what puts the rules that read a position under the same claim as the rest.
    """
    model: type[FrozenFlexModel] = type(record)
    return record.model_copy(
        update={name: turned(getattr(record, name)) for name in model.model_fields}
    )


def turned(value: FactValue) -> FactValue:
    """Return one field value with every list beneath it stated in the opposite order."""
    if isinstance(value, list):
        return [turned(item) for item in reversed(value)]
    if isinstance(value, FrozenFlexModel):
        return reversed_records(value)
    return value


def inside(value: RuleValue, definition: RuleDefinition) -> bool:
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


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_every_rule_answers_inside_the_contract_it_declares(data: st.DataObject) -> None:
    """A rule is total over its fact family, pure, and never leaves the domain it declared.

    Coverage says a line ran. This says the value that line produced was one the catalog promised,
    over facts nobody wrote down by hand: every field takes the domain its own annotation states,
    so a family that grows a field is explored the run after a provider declares it.

    Three claims travel together because they need the same fact. A rule answers rather than
    raising, it answers the same thing twice so nothing leaks between invocations, and the answer
    is a Boolean, a count that never went negative, a percentage inside its own scale, or a member
    of the closed set the rule named.
    """
    for family in FAMILIES:
        subject = data.draw(facts_of(family), label=family.__name__)
        for rule, definition in READERS[family]:
            value = answered(synchronous(rule.invoke(subject, settings={}, dependencies={})))
            again = answered(synchronous(rule.invoke(subject, settings={}, dependencies={})))

            assert again == value, f"{definition.id} answered twice and disagreed with itself"
            assert inside(value, definition), (
                f"{definition.id} declares {definition.output} and answered {value!r}"
            )


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_a_rule_reads_its_records_rather_than_the_order_they_arrived_in(
    data: st.DataObject,
) -> None:
    """A fact states a set of records and a list is only how they were carried.

    Nothing promises a provider the order it discovered files, symbols, or edges in, so a rule
    reading the first record, sorting by nothing, or folding a set into a list has written an
    answer that moves when the kernel changes its traversal. Reversing every list the fact holds,
    all the way down through the records inside records, is the cheapest transformation that must
    not matter, and the two rules it is allowed to matter for say why in the ledger.
    """
    for family in FAMILIES:
        subject = data.draw(facts_of(family), label=family.__name__)
        flipped = reversed_records(subject)
        if flipped == subject:
            continue
        for rule, definition in READERS[family]:
            if definition.id in ORDERED:
                continue
            stated = answered(synchronous(rule.invoke(subject, settings={}, dependencies={})))
            reversed_answer = answered(
                synchronous(rule.invoke(flipped, settings={}, dependencies={}))
            )

            assert stated == reversed_answer, (
                f"{definition.id} answered {stated!r} and then {reversed_answer!r} for the same "
                f"records in the opposite order"
            )


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_a_migrated_rule_states_findings_that_agree_with_the_value_it_answered(
    data: st.DataObject,
) -> None:
    """The evidence beside a value has to be about that value, for any fact at all.

    `tests/test_rule_findings.py` proves each migrated rule says the right sentence about one
    written project. This proves the shape holds everywhere: an occurrence names its finding or
    denies the defect, every measurement is a real number on the scale it declares, and a rule
    that already ships a default fix leaves the repair to it rather than offering a second one.
    """
    for family in FAMILIES:
        subject = data.draw(facts_of(family), label=family.__name__)
        for rule, definition in READERS[family]:
            if not reports_findings(rule.hints["return"]):
                continue
            outcome = synchronous(rule.invoke(subject, settings={}, dependencies={}))
            value, findings = answered(outcome), explained(outcome)
            default = any(fix.is_default for fix in definition.fixes)

            if isinstance(value, bool):
                assert bool(findings) is value, (
                    f"{definition.id} answered {value!r} beside {len(findings)} findings"
                )
            for finding in findings:
                assert finding.message.strip(), f"{definition.id} stated a finding saying nothing"
                assert not (default and finding.repair), (
                    f"{definition.id} offers a repair beside the default fix it declares"
                )
                for item in finding.measurements:
                    scaled = item.unit is not Unit.PERCENTAGE or 0.0 <= item.value <= 100.0
                    assert math.isfinite(item.value), (
                        f"{definition.id} measured {item.name} as {item.value}"
                    )
                    assert scaled, f"{definition.id} measured {item.name} outside a percentage"


def test_the_ledgers_name_exactly_the_rules_a_fact_can_still_catch_out() -> None:
    """Every order-sensitive rule is held by the fact that excuses it, so no ledger can rot.

    A ledger that only ever grew would be an allowance nobody reads. Each entry here carries the
    witness that proves it. `ORDERED` names a position that is genuinely meaningful instead of
    quietly excluding its readers from the property above.
    """
    link = OverrideFact(
        key="override:shop.Report",
        span=SourceSpan(path="shop/records.py"),
        derived="shop.Report",
        base="shop.Record",
        depth=1,
        base_names=["Record", "Row"],
        ancestor_names=["Record", "Row"],
        initializer_calls=["Stranger"],
    )
    transposed = link.model_copy(update={"base_names": ["Row", "Record"]})

    assert set(ORDERED) == {"ALL-CLAS0009", "ALL-OVER0007"}
    assert all(ORDERED.values())
    assert (ancestor_count(link), ancestor_count(transposed)) == (2, 0)
    assert (
        initializer_called_on_a_stranger(link),
        initializer_called_on_a_stranger(transposed),
    ) == (1, 0), "this rule no longer reads the base its link names"


def test_fact_models_refuse_values_that_could_escape_a_rule_contract() -> None:
    """A provider cannot state a negative count or a numerator larger than its denominator."""
    with pytest.raises(ValidationError, match="repeats 10 lines"):
        CloneGroupFact(
            key="clones:shop",
            span=SourceSpan(path="shop/left.py"),
            repository_line_count=4,
            fragments=[
                CloneFragment(path="shop/left.py", line_count=10),
                CloneFragment(path="shop/right.py", line_count=10),
            ],
        )
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ComprehensionFact(
            key="comprehensions:shop/service.py",
            span=SourceSpan(path="shop/service.py"),
            loop_counts=[-2],
        )
    with pytest.raises(ValidationError, match="2 escape hatches"):
        ModuleSurfaceFact(
            key="surface:src/index.ts",
            span=SourceSpan(path="src/index.ts"),
            physical_line_count=1,
            escape_hatches=[EscapeHatch(kind="any"), EscapeHatch(kind="any")],
        )
    with pytest.raises(ValidationError, match="beyond its physical lines"):
        ModuleSurfaceFact(
            key="surface:src/index.ts",
            span=SourceSpan(path="src/index.ts"),
            physical_line_count=2,
            escape_hatches=[EscapeHatch(kind="any", line=3)],
        )


def test_the_sweep_reaches_every_rule_that_answers_from_one_fact_alone() -> None:
    """A sweep silently covering half the catalog would read exactly like a sweep that passed."""
    catalog = built_catalog()
    swept = {definition.id for readers in READERS.values() for _, definition in readers}
    deterministic = {item.id for item in catalog.definitions if item.lane == "deterministic"}

    assert swept == deterministic
    assert len(swept) == 214
    assert len(FAMILIES) == 63
