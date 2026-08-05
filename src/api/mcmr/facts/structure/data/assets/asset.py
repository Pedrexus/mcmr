from typing import Literal

from patos import FrozenModel

from .field import DataField


class DataAsset(FrozenModel):
    """Retain one catalog asset and its governance metadata."""

    identifier: str
    description: str = ""
    owners: list[str] = []
    domain: str = ""
    lifecycle: Literal["active", "deprecated", "removed", "unknown"] = "unknown"
    is_changed: bool = False
    fields: list[DataField] = []
