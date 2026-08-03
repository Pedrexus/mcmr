from patos import FrozenModel
from pydantic import NonNegativeInt

from .....domain.primitives import NonEmptyStr


class RunbookTriggerFields(FrozenModel):
    """Retain trigger identity, scope, ownership, commands, and verification."""

    name: NonEmptyStr
    in_scope: bool = True
    owner: str = ""
    prerequisites: list[str] = []
    commands: list[str] = []
    verification_age_days: NonNegativeInt | None = None
    self_healing: bool = False
