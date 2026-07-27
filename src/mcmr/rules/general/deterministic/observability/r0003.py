from ..... import rule
from .....facts import AlertFact
from .....models import Percentage


@rule
def alert_actionability(
    subject: AlertFact,
) -> Percentage:
    """Measure alerts with enough information for an owned response.

    Definition
    ----------
    Divide enabled paging alerts that meet every configured actionability field by all enabled
    paging alerts and return the percentage.

    Evidence
    --------
    Findings retain alert condition, impact, owner, destination, runbook, and recent outcomes. The
    value is the percentage of enabled paging alerts meeting every actionability field.

    Exceptions
    ----------
    An informational notification stays out of the denominator entirely, since nothing about it is
    supposed to wake anybody and holding it to a paging alert's contract would depress the number
    without improving a response. A disabled alert is excluded for the same reason. An alert that
    names an owner who has since left still counts as owned here, because the roster is evidence
    this rule does not hold.

    Examples
    --------
    Eighteen actionable paging alerts among twenty produce `90`. An alert with no owner or response
    path does not count.

    References
    ----------
    Cites "Site Reliability Engineering", monitoring distributed systems
    Cites "The Site Reliability Workbook", alerting on SLOs
    Cites "Prometheus documentation", alerting best practices
    """
    return subject.alerts.coverage("owner", "severity", "condition", "action", "runbook")
