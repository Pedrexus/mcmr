import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr import Boolean, Category, Numeric, RulePolicies
from mcmr.domain.contracts import RuleDefinition, RuleDocumentation, RuleIdentity, RuleScope
from mcmr.domain.policy import Verdict
from mcmr.rules.general import ModuleCohesion

_DOCUMENTATION = RuleDocumentation(summary="s", definition="d", examples="e", references=["r"])

_VALUES = st.one_of(
    st.booleans(),
    st.integers(min_value=-20, max_value=2000),
    st.floats(min_value=-20.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    st.sampled_from(["cohesive", "mixed", "uncertain", "not_applicable", ""]),
)


def definition(
    identifier: str,
    *,
    output: str,
    unit: str = "",
    policy: Numeric | Boolean | Category | None = None,
) -> RuleDefinition:
    """Build one rule definition the policy layer can decide about."""
    owned_policy = policy
    if owned_policy is None and output == "bool":
        owned_policy = Boolean()
    elif owned_policy is None and output == "int":
        owned_policy = Numeric(maximum=0)
    return RuleDefinition(
        identity=RuleIdentity(
            id=identifier,
            callable="mcmr.rules.general.deterministic.functions.r0001.example",
            scope=RuleScope.GENERAL,
            lane="deterministic",
            family="functions",
            fact="FunctionFact",
        ),
        output=output,
        unit=unit,
        policy=owned_policy,
        documentation=_DOCUMENTATION,
    )


@given(value=_VALUES)
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
    category = Category(good={"cohesive"}, neutral={"uncertain"}, bad={"mixed"})
    numbered = isinstance(value, int | float) and not isinstance(value, bool)

    assert (numeric.verdict(value) is Verdict.UNASSESSED) is not numbered
    assert (boolean.verdict(value) is Verdict.UNASSESSED) is not isinstance(value, bool)
    if isinstance(value, str):
        expected = {
            "cohesive": Verdict.PASS,
            "mixed": Verdict.FAIL,
            "uncertain": Verdict.UNASSESSED,
        }.get(value, Verdict.UNASSESSED)
        assert category.verdict(value) is expected
    else:
        assert category.verdict(value) is Verdict.UNASSESSED
    assert (
        numeric.verdict(value) is not Verdict.FAIL or not 0 <= float(value) <= 100,
        boolean.verdict(value) is not Verdict.PASS or value is False,
        category.verdict(value) is not Verdict.PASS or value == "cohesive",
    ) == (True, True, True)


@given(
    minimum=st.integers(min_value=0, max_value=50),
    width=st.integers(min_value=0, max_value=50),
    value=st.integers(min_value=-20, max_value=120),
)
def test_a_numeric_policy_passes_exactly_the_closed_interval_it_states(
    *, minimum: int, width: int, value: int
) -> None:
    """The interval is closed at both ends, which is the whole content of the policy."""
    bounded = Numeric(minimum=minimum, maximum=minimum + width)

    assert (bounded.verdict(value) is Verdict.PASS) is (minimum <= value <= minimum + width)
    assert Numeric(maximum=minimum + width).verdict(value) is not Verdict.FAIL or (
        value > minimum + width
    )
    assert Numeric().verdict(value) is Verdict.PASS

    with pytest.raises(ValueError, match="minimum cannot exceed maximum"):
        Numeric(minimum=2, maximum=1)


def test_rule_policies_apply_without_a_second_mode_axis() -> None:
    """Every rule contract is judged directly without a selectable policy mode."""
    lines = definition(
        "ALL-MODU0001",
        output="int",
        unit="count",
        policy=Numeric(maximum=500),
    )
    findings = definition("ALL-PARA0001", output="int", unit="count")
    coverage = definition(
        "ALL-CI0002",
        output="float",
        unit="percentage",
        policy=Numeric(minimum=95),
    )

    assert (
        RulePolicies().decide(
            500,
            rule_id=lines.id,
            candidate=lines.policy,
        )
        is Verdict.PASS
    )
    assert (
        RulePolicies().decide(
            501,
            rule_id=lines.id,
            candidate=lines.policy,
        )
        is Verdict.FAIL
    )
    assert (
        RulePolicies().decide(
            1,
            rule_id=findings.id,
            candidate=findings.policy,
        )
        is Verdict.FAIL
    )
    assert (
        RulePolicies().decide(
            0,
            rule_id=findings.id,
            candidate=findings.policy,
        )
        is Verdict.PASS
    )
    assert (
        RulePolicies().decide(
            95.0,
            rule_id=coverage.id,
            candidate=coverage.policy,
        )
        is Verdict.PASS
    )
    assert (
        RulePolicies().decide(
            90.0,
            rule_id=coverage.id,
            candidate=coverage.policy,
        )
        is Verdict.FAIL
    )


def test_an_occurrence_is_judged_by_its_rule_policy() -> None:
    """An occurrence rule names one defect, so its absence is not a matter of taste."""
    occurrence = definition("PY-IMPO0003", output="bool")

    assert (
        RulePolicies().decide(
            True,
            rule_id=occurrence.id,
            candidate=occurrence.policy,
        )
        is Verdict.FAIL
    )
    assert (
        RulePolicies().decide(
            False,
            rule_id=occurrence.id,
            candidate=occurrence.policy,
        )
        is Verdict.PASS
    )


def test_a_shape_without_a_rule_policy_is_never_judged() -> None:
    """Leave an unconfigured result shape unassessed.

    A closed category means nothing until a project says which members it lives with, and a result
    shape no policy covers stays unassessed rather than guessed.
    """
    judgment = definition("ALL-ARCH0001", output="category")
    accepting = RulePolicies(
        overrides={judgment.id: Category(good={"cohesive"}, neutral={"uncertain"}, bad={"mixed"})},
    )

    assert (
        RulePolicies().decide(
            "mixed",
            rule_id=judgment.id,
            candidate=judgment.policy,
        ),
        accepting.decide(
            "cohesive",
            rule_id=judgment.id,
            candidate=judgment.policy,
        ),
        accepting.decide(
            "mixed",
            rule_id=judgment.id,
            candidate=judgment.policy,
        ),
    ) == (Verdict.UNASSESSED, Verdict.PASS, Verdict.FAIL)
    unstated = definition("ALL-X0001", output="str")
    assert (
        RulePolicies().decide(
            "text",
            rule_id=unstated.id,
            candidate=unstated.policy,
        )
        is Verdict.UNASSESSED
    )

    with pytest.raises(ValueError, match="at least one category"):
        Category()

    with pytest.raises(ValueError, match="must be disjoint"):
        Category(good={"same"}, bad={"same"})


def test_category_outcomes_close_one_rule_enum_without_repeating_its_bad_members() -> None:
    policy = Category.outcomes(
        ModuleCohesion,
        good={ModuleCohesion.COHESIVE, ModuleCohesion.INTENTIONAL_INTEGRATION},
        neutral={ModuleCohesion.UNCERTAIN},
    )

    assert policy.good == {"cohesive", "intentional_integration"}
    assert policy.neutral == {"uncertain"}
    assert policy.bad == {"mixed"}
