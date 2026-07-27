import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr.models import RuleDefinition, RuleDocumentation, RuleScope
from mcmr.policy import (
    Boolean,
    Category,
    Numeric,
    Profile,
    Verdict,
    profiles,
    relaxed,
    standard,
    strict,
)
from tests.conftest import built_catalog

DOCUMENTATION = RuleDocumentation(summary="s", definition="d", examples="e", references=["r"])

VALUES = st.one_of(
    st.booleans(),
    st.integers(min_value=-20, max_value=2000),
    st.floats(min_value=-20.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    st.sampled_from(["cohesive", "mixed", "uncertain", "not_applicable", ""]),
)


def definition(identifier: str, output: str, unit: str = "") -> RuleDefinition:
    """Build one rule definition the policy layer can decide about."""
    return RuleDefinition(
        id=identifier,
        callable="mcmr.rules.general.deterministic.functions.r0001.example",
        scope=RuleScope.GENERAL,
        lane="deterministic",
        family="functions",
        fact="FunctionFact",
        output=output,
        unit=unit,
        documentation=DOCUMENTATION,
    )


@given(value=VALUES)
def test_a_policy_decides_the_shape_it_was_written_for_and_abstains_on_every_other(
    value: bool | int | float | str,
) -> None:
    """A policy reaching a verdict about a shape it cannot read would be a guess with a name.

    Each of the three is total over every value a rule can answer with, and each abstains on
    exactly the values of another shape. The Boolean case is the one worth stating twice, since
    `True` is an `int` in Python and a numeric interval that accepted it would silently judge every
    occurrence rule in the catalog against a magnitude nobody chose.
    """
    numeric, boolean = Numeric(minimum=0, maximum=100), Boolean()
    category = Category(accepted=frozenset({"cohesive"}))
    numbered = isinstance(value, int | float) and not isinstance(value, bool)

    assert (numeric.verdict(value) is Verdict.UNASSESSED) is not numbered
    assert (boolean.verdict(value) is Verdict.UNASSESSED) is not isinstance(value, bool)
    assert (category.verdict(value) is Verdict.UNASSESSED) is not isinstance(value, str)
    assert numeric.verdict(value) is not Verdict.FAIL or not 0 <= float(value) <= 100
    assert boolean.verdict(value) is not Verdict.PASS or value is False
    assert category.verdict(value) is not Verdict.PASS or value == "cohesive"


@given(value=VALUES)
def test_a_profile_never_loosens_as_it_tightens(value: bool | int | float | str) -> None:
    """Strictness is an order, so anything the standard profile refuses the strict one refuses.

    A profile is a table of thresholds a person edits, and the one mistake that table invites is a
    strict entry looser than the standard entry beside it. Nothing about the shape of a `Profile`
    prevents that, so it is checked against the whole catalog rather than against the handful of
    identifiers a reader thought to name.
    """
    ordered = [relaxed(), standard(), strict()]
    for item in built_catalog().definitions:
        verdicts = [profile.decide(item, value) for profile in ordered]
        for looser, tighter in zip(verdicts, verdicts[1:], strict=False):
            assert looser is not Verdict.FAIL or tighter is Verdict.FAIL, (
                f"{item.id} fails one profile at {value!r} and passes a stricter one"
            )


@given(
    minimum=st.integers(min_value=0, max_value=50),
    width=st.integers(min_value=0, max_value=50),
    value=st.integers(min_value=-20, max_value=120),
)
def test_a_numeric_policy_passes_exactly_the_closed_interval_it_states(
    minimum: int, width: int, value: int
) -> None:
    """The interval is closed at both ends, which is the whole content of the policy."""
    bounded = Numeric(minimum=minimum, maximum=minimum + width)

    assert (bounded.verdict(value) is Verdict.PASS) is (minimum <= value <= minimum + width)
    assert Numeric(maximum=minimum + width).verdict(value) is not Verdict.FAIL or (
        value > minimum + width
    )
    assert Numeric().verdict(value) is Verdict.PASS


def test_a_measurement_stays_unassessed_until_a_project_states_an_interval() -> None:
    """Nothing but a project can say which magnitude it accepts, so nothing else decides.

    The three shapes each carry their own direction. A module length is a magnitude no profile
    below `standard` judges, a count is a count of findings unless the rule measures something, and
    a percentage is coverage judged by a floor rather than a density judged by a ceiling.
    """
    lines = definition("ALL-MODU0001", "int", "count")
    findings = definition("ALL-PARA0001", "int", "count")
    coverage = definition("ALL-CI0002", "float", "percentage")

    assert relaxed().decide(lines, 1410) is Verdict.UNASSESSED
    assert standard().decide(lines, 300) is Verdict.PASS
    assert strict().decide(lines, 400) is Verdict.FAIL
    assert standard().decide(findings, 1) is Verdict.FAIL
    assert standard().decide(findings, 0) is Verdict.PASS
    assert standard().decide(coverage, 90.0) is Verdict.PASS
    assert strict().decide(coverage, 90.0) is Verdict.FAIL


def test_an_occurrence_is_judged_the_same_at_every_strictness() -> None:
    """An occurrence rule names one defect, so its absence is not a matter of taste."""
    occurrence = definition("PY-IMPO0003", "bool")

    assert [profile.decide(occurrence, True) for profile in profiles().values()] == [
        Verdict.FAIL
    ] * 3
    assert relaxed().decide(occurrence, False) is Verdict.PASS


def test_a_shape_no_profile_states_a_policy_for_is_never_judged() -> None:
    """A closed category means nothing until a project says which members it lives with, and a
    result shape no policy covers stays unassessed rather than guessed."""
    judgment = definition("ALL-ARCH0001", "category")
    accepting = Profile(name="own", categories=Category(accepted=frozenset({"cohesive"})))

    assert standard().decide(judgment, "mixed") is Verdict.UNASSESSED
    assert accepting.decide(judgment, "cohesive") is Verdict.PASS
    assert accepting.decide(judgment, "mixed") is Verdict.FAIL
    assert Profile(name="own").decide(definition("ALL-X0001", "str"), "text") is Verdict.UNASSESSED

    with pytest.raises(ValueError, match="at least 1 item"):
        Category(accepted=frozenset())
