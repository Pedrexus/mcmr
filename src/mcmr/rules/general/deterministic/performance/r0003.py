from ..... import rule
from .....facts import PerformanceDecisionFact
from .....models import Percentage


@rule
def regression_guard_coverage(
    subject: PerformanceDecisionFact,
) -> Percentage:
    """Measure critical performance budgets protected by repeatable regression checks.

    Definition
    ----------
    Divide declared critical performance budgets with representative automated comparisons and
    controlled baselines by all declared critical budgets and return the percentage.

    Evidence
    --------
    Findings retain budget, workload, environment, baseline, variance policy, and check outcome.
    The value is the percentage of critical budgets protected by a repeatable regression check.

    Exceptions
    ----------
    Expensive system benchmarks may run asynchronously when regressions still have an owned gate.

    Examples
    --------
    Nine protected budgets among ten produce `90`. A benchmark with no baseline or variance policy
    does not count as a regression guard.

    References
    ----------
    Cites "Systems Performance"
    Cites "pytest-benchmark documentation"
    Cites "Google Benchmark documentation"
    """
    return subject.budgets.coverage(
        "representative_comparison", "controlled_baseline", "automated"
    )
