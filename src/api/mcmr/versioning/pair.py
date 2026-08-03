from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt, PositiveInt, model_validator

from ..domain.primitives import NonEmptyStr

if TYPE_CHECKING:
    from typing import Self


class CoChangedPair(FrozenModel):
    """Derive two files that arrive in the same focused commits and reference each other."""

    left: NonEmptyStr
    right: NonEmptyStr
    shared_commit_count: PositiveInt
    left_commit_count: PositiveInt
    right_commit_count: PositiveInt
    import_reference_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def shared_commits_fit_each_file(self) -> Self:
        """Reject support greater than either file's own focused commit count."""
        if self.left == self.right:
            raise ValueError("a file cannot be co-changed with itself")
        if self.shared_commit_count > min(self.left_commit_count, self.right_commit_count):
            raise ValueError("shared commits cannot outnumber either file's commits")
        return self
