from patos import FrozenModel
from pydantic import NonNegativeInt


class QuarantinedTest(FrozenModel):
    """Retain one quarantined test and its remediation evidence."""

    name: str
    age_days: NonNegativeInt | None = None
    owner: str = ""
    has_remediation_evidence: bool = False
    recurred_after_repair: bool = False
