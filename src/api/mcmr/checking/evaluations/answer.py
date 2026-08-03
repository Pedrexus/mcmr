from patos import FrozenModel

from ...domain.contracts import Finding, Observation, RuleValue
from ...facts import SourceSpan


class Evaluation(FrozenModel):
    """Carry one validated rule answer without constructing a public report model."""

    rule: str
    fact: str
    value: RuleValue
    span: SourceSpan
    findings: list[Finding]

    def observation(self) -> Observation:
        """Materialize the public model only when a retained verdict needs it."""
        return Observation.model_validate(self, from_attributes=True)
