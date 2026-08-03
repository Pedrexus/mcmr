from patos import FrozenModel


class DataChange(FrozenModel):
    """Retain one schema change and its transitive impact evidence."""

    asset_identifier: str
    is_breaking: bool
    downstream_assets: list[str] = []
    tested_assets: list[str] = []
