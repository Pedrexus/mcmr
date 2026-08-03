from typing import TYPE_CHECKING, Literal

from .groups import ArchitectureFields

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class ArchitectureCharacteristic(ArchitectureFields):
    """Retain raw evidence declared for one architecture quality."""

    owner: str = ""
    scope: str = ""
    observation_age_days: NonNegativeInt | None = None
    verification: Literal["ci", "manual", "repeatable_review", "none"] = "none"
