from typing import Literal

from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class AlertDefinitionFields(FrozenModel):
    """Retain alert identity, audience, condition, severity, impact, and owner."""

    name: NonEmptyStr
    enabled: bool = True
    audience: Literal["paging", "informational"] = "paging"
    condition: str = ""
    severity: str = ""
    impact: str = ""
    owner: str = ""
