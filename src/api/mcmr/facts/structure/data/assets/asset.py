from patos import FrozenModel

from .field import DataField


class DataAsset(FrozenModel):
    """Retain one catalog asset and its governance metadata."""

    identifier: str
    description: str = ""
    owners: list[str] = []
    domain: str = ""
    is_changed: bool = False
    fields: list[DataField] = []
