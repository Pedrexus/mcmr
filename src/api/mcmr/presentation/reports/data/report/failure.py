from .....domain.contracts import Finding, RuleValue
from .groups import CheckReportFields


class RuleFailure(CheckReportFields.FailureIdentity):
    """Retain one failed rule with everything a reader or agent acts on."""

    value: RuleValue
    allowed: str
    findings: list[Finding] = []

    @property
    def reported(self) -> list[Finding]:
        """Return its findings or one summary finding when no detail exists."""
        return list(self.findings) or [Finding(message=self.summary, span=self.span)]

    @classmethod
    def of(cls, assessment: CheckReportFields.Assessment, bar: str) -> RuleFailure:
        """Return the failure one judged assessment states."""
        return cls(
            rule=assessment.definition.id,
            callable=assessment.definition.callable,
            summary=assessment.definition.documentation.summary,
            where=assessment.observation.fact,
            span=assessment.observation.span,
            value=assessment.observation.value,
            allowed=bar,
            findings=assessment.observation.findings,
        )
