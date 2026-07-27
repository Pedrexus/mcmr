from ..... import rule
from .....facts import ServiceObjectiveFact
from .....models import Percentage


@rule
def service_objective_coverage(
    subject: ServiceObjectiveFact,
) -> Percentage:
    """Measure owned user-facing services with defined service objectives.

    Definition
    ----------
    Divide in-scope user-facing services with an owner, indicators, objectives, windows, and error
    budget policy by all in-scope user-facing services and return the percentage.

    Evidence
    --------
    Findings retain service, owner, user journey, indicators, objectives, windows, and policy. The
    value is the percentage of in-scope services carrying a complete objective.

    Exceptions
    ----------
    Offline libraries and internal experiments may use explicit reliability targets instead.

    Examples
    --------
    Four fully specified services among five produce `80`. A dashboard without an objective or
    window does not satisfy the rule.

    References
    ----------
    Cites "Site Reliability Engineering", Service Level Objectives
    Cites "The Site Reliability Workbook", implementing SLOs
    Cites "Observability Engineering", SLOs across the lifecycle
    """
    return subject.services.coverage(
        "owner", "indicators", "objectives", "windows", "error_budget_policy"
    )
