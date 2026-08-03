from patos import FrozenModel
from pydantic import Field, PositiveInt

from .....domain.primitives import NonEmptyStr
from .replacement import CapabilityReplacement


class CapabilityMigration(FrozenModel):
    """Hold every declared product capability replacement."""

    schema_version: PositiveInt = Field(alias="schema")
    source: NonEmptyStr
    target: NonEmptyStr
    capabilities: list[CapabilityReplacement]
