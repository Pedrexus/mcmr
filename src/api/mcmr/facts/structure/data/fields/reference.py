from patos import FrozenModel


class DataFieldReference(FrozenModel):
    """Retain one source field reference and exact schema resolution."""

    source_location: str
    asset_identifier: str
    field_name: str
    asset_exists: bool
    field_exists: bool
    expected_type: str = ""
    catalog_type: str = ""
