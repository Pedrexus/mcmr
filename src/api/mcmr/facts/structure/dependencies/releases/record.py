from typing import TYPE_CHECKING

from pydantic import model_validator

from .groups import DependencyRecordFields

if TYPE_CHECKING:
    from typing import Self


class DependencyRecord(DependencyRecordFields):
    """Retain exact package and source state from dependency evidence."""

    is_development: bool = False

    @model_validator(mode="after")
    def latest_release_is_not_older(self) -> Self:
        """Require the latest compatible release not to predate the resolved one."""
        if (
            self.resolved_release_day is not None
            and self.latest_compatible_release_day is not None
            and self.latest_compatible_release_day < self.resolved_release_day
        ):
            raise ValueError("latest compatible release predates the resolved release")
        return self
