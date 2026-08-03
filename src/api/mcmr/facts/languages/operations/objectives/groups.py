from patos import FrozenModel

from .....domain.primitives import NonEmptyStr


class ServiceObjectiveFields(FrozenModel):
    """Retain service identity, scope, ownership, and objective evidence."""

    name: NonEmptyStr
    in_scope: bool = True
    user_facing: bool = True
    owner: str = ""
    user_journeys: list[str] = []
    indicators: list[str] = []
    objectives: list[str] = []
