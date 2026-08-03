from patos import FrozenModel
from pydantic import Field, PositiveInt

from ....domain.primitives import NonEmptyStr
from .legacy import LegacyRule


class LegacyRuleInventory(FrozenModel):
    """Hold the complete frozen rule inventory from the product MCMR replaces."""

    schema_version: PositiveInt = Field(alias="schema")
    product: NonEmptyStr
    rules: list[LegacyRule]
