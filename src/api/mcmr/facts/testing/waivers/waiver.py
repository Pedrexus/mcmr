from patos import FrozenModel
from pydantic import NonNegativeInt


class Waiver(FrozenModel):
    """Retain one suppression and its exact lifecycle metadata."""

    location: str
    age_days: NonNegativeInt | None = None
    expires_in_days: int | None = None
    is_overly_broad: bool = False
    metadata: dict[str, str] = {}
