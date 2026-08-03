from typing import Annotated

from patos import FrozenModel
from pydantic import Field, JsonValue

from ...domain.contracts import RuleId
from ...domain.primitives import NonEmptyStr
from ...execution import ModelCandidate
from ...facts import Evidence
from .expectation import ContextualExpectation


class ContextualCase(FrozenModel):
    """Hold one reviewed candidate and its exact expected contextual answer."""

    name: NonEmptyStr
    rule: RuleId
    fact_id: NonEmptyStr
    path: NonEmptyStr
    subject: JsonValue
    evidence: Annotated[list[Evidence], Field(min_length=1)]
    expected: ContextualExpectation

    @property
    def candidate(self) -> ModelCandidate:
        """Build the transport object every backend receives from the frozen label."""
        return ModelCandidate(
            fact_id=self.fact_id,
            path=self.path,
            subject=self.subject,
            evidence=list(self.evidence),
        )
