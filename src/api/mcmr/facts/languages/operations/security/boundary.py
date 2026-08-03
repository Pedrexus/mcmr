from typing import TYPE_CHECKING

from .groups import SecurityBoundaryFields

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class SecurityBoundary(SecurityBoundaryFields):
    """Retain one boundary before contextual threat analysis."""

    residual_risks: list[str] = []
    owner: str = ""
    review_age_days: NonNegativeInt | None = None
    inherited_model: str = ""
