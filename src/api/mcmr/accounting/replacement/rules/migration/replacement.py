from patos import FrozenModel
from pydantic import model_validator

from .....domain.primitives import NonEmptyStr


class RuleReplacement(FrozenModel):
    """Map one frozen GE4M rule to the MCMR rules that answer for it."""

    source_id: NonEmptyStr
    target_ids: list[NonEmptyStr] = []
    relation: NonEmptyStr

    @model_validator(mode="after")
    def retirement_has_no_successor(self) -> RuleReplacement:
        """Require a live target unless the obsolete rule is explicitly retired."""
        retired = self.relation == "retired"
        if retired == bool(self.target_ids):
            expectation = "no targets" if retired else "at least one target"
            raise ValueError(f"{self.source_id} relation {self.relation} needs {expectation}")
        return self
