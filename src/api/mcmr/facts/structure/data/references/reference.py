from typing import Literal

from patos import FrozenModel
from pydantic import Field


class DataAssetReference(FrozenModel):
    """Retain one source reference and its exact catalog resolution."""

    source_location: str
    asset_identifier: str
    asset_exists: bool
    lifecycle: Literal["active", "deprecated", "removed", "unknown"] = "unknown"
    upstream_health: dict[str, Literal["healthy", "unhealthy", "unknown"]] = Field(
        default_factory=dict
    )
