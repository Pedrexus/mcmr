from typing import Annotated

from patos import FrozenModel
from pydantic import Field, NonNegativeInt, field_validator

from ....domain.primitives import NonEmptyStr


class HistoryChange(FrozenModel):
    """Retain one commit's requested paths and its repository-wide width."""

    other_file_count: NonNegativeInt = 0
    paths: Annotated[list[NonEmptyStr], Field(min_length=1)]

    @property
    def changed_file_count(self) -> int:
        """Return the commit's full width without storing a second count."""
        return len(self.paths) + self.other_file_count

    @field_validator("paths")
    @classmethod
    def paths_fit_commit(cls, paths: list[NonEmptyStr]) -> list[NonEmptyStr]:
        """Reject duplicate or excess paths that no real commit can carry."""
        if len(set(paths)) != len(paths):
            raise ValueError("one commit cannot repeat a changed path")
        return paths
