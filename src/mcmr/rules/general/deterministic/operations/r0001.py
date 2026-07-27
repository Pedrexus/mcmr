from ..... import rule
from .....facts import RunbookFact
from .....models import Percentage


@rule
def runbook_coverage(
    subject: RunbookFact,
) -> Percentage:
    """Measure operational triggers linked to current executable guidance.

    Definition
    ----------
    Divide in-scope alerts, manual operations, and recovery scenarios with owned and recently
    verified runbooks by all in-scope triggers and return the percentage.

    Evidence
    --------
    Findings retain trigger, runbook, owner, prerequisites, commands, verification, and age. The
    value is the percentage of in-scope triggers carrying an owned and recently verified runbook.

    Exceptions
    ----------
    Fully automated self-healing paths may link to design and verification evidence instead.

    Examples
    --------
    Nine covered triggers among ten produce `90`. A stale document naming removed commands does
    not count as verified guidance.

    References
    ----------
    Cites "Site Reliability Engineering", effective troubleshooting
    Cites "The Site Reliability Workbook", on-call and incident response
    Cites "Incident Management for Operations", runbook practices
    """
    return subject.triggers.coverage("owner", "recent_verification")
