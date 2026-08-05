from patos import FrozenModel
from pydantic import NonNegativeInt, PositiveInt

from ....domain.primitives import NonEmptyStr


class FileHistory(FrozenModel):
    """Retain how often one file changed, by how many hands, and how long ago."""

    path: NonEmptyStr
    author_count: PositiveInt = 1
    additional_commit_count: NonNegativeInt = 0
    days_since_last_change: NonNegativeInt = 0
    line_count: NonNegativeInt = 0
    is_test: bool = False
    imports: list[str] = []

    @property
    def commit_count(self) -> int:
        """Return all file commits without storing an impossible author relationship."""
        return self.author_count + self.additional_commit_count
