import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....facts import FeatureFlagFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-LIFE0002")
def feature_flag_debt(
    subject: Table[FeatureFlagFact],
    *,
    maximum_age_days: NonNegativeInt = 90,
    permanent_labels: tuple[str, ...] = ("operational", "permission"),
) -> CountQuery:
    """Count feature flags that lack a current lifecycle decision.

    Definition
    ----------
    Count flags whose decision date is due or whose age exceeds the threshold without an explicit
    permanent role, owner, tested states, and cleanup plan. The result measures stale control
    paths rather than all flags.

    Evidence
    --------
    Findings retain declaration, states, owner, creation, decision date, usage, and cleanup plan.
    The value is the number of flags past their decision without a permanent role.

    Exceptions
    ----------
    Permanent operational and permission controls remain valid when labeled, owned, tested in at
    least two states, and governed by a cleanup plan.
    `maximum_age_days` is how long a flag may live without a decision and `permanent_labels` names
    the roles that are allowed to live forever, which are the operational and permission controls a
    system genuinely needs.

    Examples
    --------
    Three expired experiment flags without owners produce `3`. A documented permanent emergency
    control does not count.

    References
    ----------
    Cites "Feature Toggles"
    Cites "Feature Toggles", categories and carrying cost
    Cites "Software Engineering at Google", deprecation and change management
    """
    relations = subject
    decision_due = pl.col("decision_due_days").is_not_null() & (pl.col("decision_due_days") <= 0)
    permanent = pl.all_horizontal(
        pl.col("role").is_in(permanent_labels),
        pl.col("owner").str.strip_chars() != "",
        pl.col("tested_states.length") >= 2,
        pl.col("cleanup_plan").str.strip_chars() != "",
    )
    selected = relations.records("flags").filter(
        (decision_due | (pl.col("age_days") > maximum_age_days)) & ~permanent
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "feature flag debt",
            evidence=pl.col("evidence"),
        ),
    )
