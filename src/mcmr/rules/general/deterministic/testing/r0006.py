from ..... import rule
from .....facts import TestStrategyFact
from .....models import Percentage


@rule
def failure_scenario_coverage(
    subject: TestStrategyFact,
) -> Percentage:
    """Measure coverage of declared and discoverable failure scenarios.

    Definition
    ----------
    Divide failure scenarios exercised with meaningful outcome assertions by all in-scope failure
    scenarios and return the percentage. Executing an exception line alone is insufficient.

    Evidence
    --------
    Findings link each failure scenario to contracts, source paths, tests, and asserted outcomes.
    The value is the percentage of in-scope failure scenarios exercised with a meaningful
    assertion.

    Exceptions
    ----------
    Physically untestable or destructive scenarios may use simulation, proof, or documented drills.

    Examples
    --------
    Eight asserted failure scenarios among ten produce `80`. A timeout path executed without
    checking rollback does not count as covered rollback behavior.

    References
    ----------
    Cites "Software Engineering at Google", Testing Overview
    Cites "Release It", stability and failure modes
    """
    return subject.failure_scenarios.coverage("exercised", "meaningful_assertion")
