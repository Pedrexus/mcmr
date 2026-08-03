from patos import FrozenModel
from pydantic import NonNegativeInt

from ....domain.contracts import ModelProvenance
from ....domain.primitives import NonEmptyStr


class ContextualSweepResult(FrozenModel):
    """Retain one contextual rule answer and the model work behind it."""

    rule: NonEmptyStr
    value: NonEmptyStr
    finding_count: NonNegativeInt
    provenance: ModelProvenance
    messages: list[str] = []
    evidence_ids: list[str] = []
    error: str = ""
