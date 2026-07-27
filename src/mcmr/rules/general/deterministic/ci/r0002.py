from ..... import rule
from .....facts import CICheckFact
from .....models import Percentage


@rule
def feedback_target_coverage(
    subject: CICheckFact, *, target_seconds: int = 600, percentile: float = 0.9
) -> Percentage:
    """Measure required CI checks meeting the configured feedback target.

    Definition
    ----------
    For each required check, compare its configured duration percentile with the feedback target.
    Return the percentage of required checks that meet the target.

    Evidence
    --------
    Findings retain workflow, check, duration distribution, queue time, and target. The value is
    the percentage of required change-blocking checks meeting the feedback target.

    Exceptions
    ----------
    Explicit asynchronous qualification suites may run outside the change-blocking feedback path.
    `target_seconds` is the feedback target a required check has to meet and `percentile` chooses
    which point of its duration distribution is compared, so a project judging its slowest runs
    raises the percentile rather than the target.

    Examples
    --------
    Nine of ten required checks meeting a ten-minute target produce `90`. A nightly soak test does
    not enter the denominator unless it blocks ordinary changes.

    References
    ----------
    Cites "Software Engineering at Google", Continuous Integration
    Cites "Accelerate", fast feedback and continuous delivery
    Cites "DORA research", continuous delivery
    """
    required = [
        check
        for check in subject.checks
        if check.is_required and check.is_change_blocking and check.percentile >= percentile
    ]
    if not required:
        return 0.0
    passing = sum(check.duration_percentile_seconds <= target_seconds for check in required)
    return passing / len(required) * 100.0
