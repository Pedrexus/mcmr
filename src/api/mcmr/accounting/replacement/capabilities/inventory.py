from patos import FrozenModel
from pydantic import Field, PositiveInt

from ....domain.primitives import NonEmptyStr
from .legacy import LegacyCapability


class CapabilityInventory(FrozenModel):
    """Hold the complete command and extension surface being replaced."""

    schema_version: PositiveInt = Field(alias="schema")
    product: NonEmptyStr
    capabilities: list[LegacyCapability]
