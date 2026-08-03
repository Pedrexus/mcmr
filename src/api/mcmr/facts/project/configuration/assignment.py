from typing import Literal

from patos import FrozenModel


class ConfigurationAssignment(FrozenModel):
    """Retain one simple collection assignment from project source."""

    name: str
    collection_kind: Literal["list", "tuple", "set", "other"]
    values: list[str] = []
    is_typed_configuration_field: bool = False
