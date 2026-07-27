from ..... import rule
from .....facts import FeatureFlagFact
from .....models import Count


@rule
def feature_flag_debt(
    subject: FeatureFlagFact,
    *,
    maximum_age_days: int = 90,
    permanent_labels: tuple[str, ...] = ("operational", "permission"),
) -> Count:
    """Count feature flags that lack a current lifecycle decision.

    Definition
    ----------
    Count flags past their intended decision date or age threshold without an explicit permanent
    role, owner, and tested states. The result measures stale control paths rather than all flags.

    Evidence
    --------
    Findings retain declaration, states, owner, creation, decision date, usage, and cleanup plan.
    The value is the number of flags past their decision without a permanent role.

    Exceptions
    ----------
    Permanent operational and permission controls remain valid when labeled, owned, and tested.
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
    return sum(
        (flag.is_past_decision_date or flag.age_days > maximum_age_days)
        and not (flag.role in permanent_labels and flag.owner and flag.has_tested_states)
        for flag in subject.flags
    )
