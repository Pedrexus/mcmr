from patos import FrozenModel
from pydantic import Field, PositiveInt

from .....domain.primitives import NonEmptyStr
from .replacement import RuleReplacement


class RuleMigration(FrozenModel):
    """Hold every declared rule replacement independently of the old inventory."""

    schema_version: PositiveInt = Field(alias="schema")
    source: NonEmptyStr
    target: NonEmptyStr
    rules: list[RuleReplacement]
