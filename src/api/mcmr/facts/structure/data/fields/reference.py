from patos import FrozenModel

from .repair import DataFieldRepair


class DataFieldReference(FrozenModel):
    """Retain one source field reference, exact schema resolution, and any proven repair."""

    asset_identifier: str
    field_name: str
    asset_exists: bool
    field_exists: bool
    expected_type: str = ""
    catalog_type: str = ""
    repair: DataFieldRepair = DataFieldRepair()
