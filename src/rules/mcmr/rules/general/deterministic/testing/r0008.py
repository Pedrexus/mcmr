import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....facts import TestFunctionFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-TEST0002")
def flaky_test_quarantine_debt(
    subject: Table[TestFunctionFact],
    *,
    maximum_age_days: NonNegativeInt = 14,
    require_owner: bool = True,
) -> CountQuery:
    """Count quarantined flaky tests without timely owned remediation.

    Definition
    ----------
    Count quarantined tests that exceed the age limit, lack a required owner, recur after claimed
    repair, or have no remediation evidence. This complements flaky-test rate without treating
    reruns or quarantine as a fix.

    Evidence
    --------
    Findings retain test identity, quarantine date, owner, outcomes, recurrence, and repair status.
    The value is the number of quarantined tests without timely owned remediation.

    Exceptions
    ----------
    A bounded quarantine may remain during an active incident when ownership and next action exist.
    `maximum_age_days` is how long a quarantine may last before it counts as debt, and setting
    `require_owner` to false accepts a quarantine nobody has been assigned, which is worth doing
    only while another record carries the ownership. Python evidence recognizes explicit
    `pytest.mark.flaky`, `pytest.mark.quarantine`, and `pytest.mark.quarantined` decorators. Their
    `since`, `owner`, `remediation`, and `recurred_after_repair` keywords carry the lifecycle
    evidence. A missing `since` is unknown age and therefore debt rather than a new quarantine.

    Examples
    --------
    Two old quarantines and one ownerless quarantine produce `3`. A three-day quarantine with an
    owner and active repair does not count.

    References
    ----------
    Cites "The Google Testing Blog", flaky tests
    Cites "Flaky Test Detection and Management at Microsoft", arXiv 2212.00908
    Cites "pytest-rerunfailures documentation"
    """
    relations = subject
    selected = relations.records("quarantined_tests").filter(
        pl.col("age_days").is_null()
        | (pl.col("age_days") > maximum_age_days)
        | (pl.lit(require_owner) & (pl.col("owner") == ""))
        | pl.col("recurred_after_repair")
        | ~pl.col("has_remediation_evidence")
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "flaky test quarantine debt",
            evidence=pl.col("evidence"),
        ),
    )
