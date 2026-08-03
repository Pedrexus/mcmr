from collections import Counter
from itertools import combinations
from typing import TYPE_CHECKING, Self

from pydantic import NonNegativeInt, model_validator

from ....versioning import CoChangedPair, FileHistory, HistoryChange
from ...foundation import Fact

if TYPE_CHECKING:
    from collections.abc import Mapping


class RepositoryHistoryFact(Fact):
    """Describe repository history for its files and commits."""

    unscoped_commit_count: NonNegativeInt = 0
    files: list[FileHistory] = []
    changes: list[HistoryChange] = []

    @property
    def commit_count(self) -> int:
        """Return all commits from retained evidence."""
        return len(self.changes) + self.unscoped_commit_count

    def coupling(self, maximum_commit_files: int) -> list[CoChangedPair]:
        """Derive exact co-change counts under the explicit sweep boundary."""
        focused = [
            sorted(change.paths)
            for change in self.changes
            if change.changed_file_count <= maximum_commit_files
        ]
        commits = Counter(path for paths in focused for path in paths)
        support = Counter(pair for paths in focused for pair in combinations(paths, 2))
        records = {record.path: record for record in self.files}
        return [
            CoChangedPair(
                left=left,
                right=right,
                shared_commit_count=shared,
                left_commit_count=commits[left],
                right_commit_count=commits[right],
                import_reference_count=self._mentions(records, reader=left, subject=right)
                + self._mentions(records, reader=right, subject=left),
            )
            for (left, right), shared in sorted(
                support.items(), key=lambda item: (-item[1], item[0])
            )
        ]

    @model_validator(mode="after")
    def history_is_internally_possible(self) -> Self:
        """Reject counts impossible under the retained commits."""
        paths = [record.path for record in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("repository history cannot repeat a file")
        if any(record.commit_count > self.commit_count for record in self.files):
            raise ValueError("a file cannot outnumber repository commits")
        return self

    @staticmethod
    def _names(line: str, *, subject: str) -> bool:
        """Whether one line states a name as a whole word."""
        start = 0
        while (position := line.find(subject, start)) >= 0:
            before = line[position - 1] if position else ""
            after_at = position + len(subject)
            after = line[after_at] if after_at < len(line) else ""
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                return True
            start = position + 1
        return False

    @staticmethod
    def _stem(path: str) -> str:
        """Return the name one file is imported under."""
        file = path.rsplit("/", 1)[-1]
        base = file.split(".", 1)[0]
        if base in {"__init__", "mod", "lib", "index", "main"}:
            return path.rsplit("/", 2)[-2] if "/" in path else base
        return base

    @classmethod
    def _mentions(
        cls,
        records: Mapping[str, FileHistory],
        *,
        reader: str,
        subject: str,
    ) -> int:
        """Count import lines naming the other file as a whole word."""
        record = records.get(reader)
        if record is None:
            return 0
        name = cls._stem(subject)
        return sum(cls._names(line, subject=name) for line in record.imports)
