from ..... import rule
from .....facts import TestSuiteFact
from .....models import Count


@rule
def flaky_test_quarantine_debt(
    subject: TestSuiteFact,
    *,
    maximum_age_days: int = 14,
    require_owner: bool = True,
) -> Count:
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
    only while another record carries the ownership.

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
    return sum(
        test.age_days > maximum_age_days
        or require_owner
        and not test.owner
        or test.recurred_after_repair
        or not test.has_remediation_evidence
        for test in subject.quarantined_tests
    )
