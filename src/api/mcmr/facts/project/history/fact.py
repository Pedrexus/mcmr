from typing import TYPE_CHECKING

from pydantic import NonNegativeInt, model_validator

from ...foundation import Fact

if TYPE_CHECKING:
    from typing import Self

    from .change import HistoryChange
    from .file import FileHistory


class RepositoryHistoryFact(Fact):
    """Describe repository history for its files and commits."""

    unscoped_commit_count: NonNegativeInt = 0
    files: list[FileHistory] = []
    changes: list[HistoryChange] = []

    @property
    def commit_count(self) -> int:
        """Return all commits from retained evidence."""
        return len(self.changes) + self.unscoped_commit_count

    @model_validator(mode="after")
    def history_is_internally_possible(self) -> Self:
        """Reject counts impossible under the retained commits."""
        paths = [record.path for record in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("repository history cannot repeat a file")
        if any(record.commit_count > self.commit_count for record in self.files):
            raise ValueError("a file cannot outnumber repository commits")
        return self
