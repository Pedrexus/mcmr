from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Self

from patos import FrozenModel
from pydantic import AfterValidator, NonNegativeInt, PositiveInt, model_validator


def _repository_relative(path: str) -> str:
    """Require the normalized repository-relative path every provider promises."""
    if "\\" in path:
        raise ValueError("source span path must use forward slashes")
    posix = PurePosixPath(path)
    windows = PureWindowsPath(path)
    if posix.is_absolute() or windows.is_absolute():
        raise ValueError("source span path must be repository relative")
    if ".." in posix.parts or ".." in windows.parts:
        raise ValueError("source span path cannot leave the repository")
    return path


class SourceSpan(FrozenModel):
    """Locate one fact in source or retained engineering evidence."""

    path: Annotated[str, AfterValidator(_repository_relative)]
    start_line: PositiveInt = 1
    start_column: NonNegativeInt = 0
    end_line: PositiveInt = 1
    end_column: NonNegativeInt = 0

    @property
    def location(self) -> str:
        """Return the exact source range a reader can paste into an editor."""
        if self.end_line > self.start_line:
            return f"{self.path}:{self.start_line}-{self.end_line}"
        return f"{self.path}:{self.start_line}"

    @model_validator(mode="before")
    @classmethod
    def close_an_omitted_end(cls, value: dict[str, str | int]) -> dict[str, str | int]:
        """Make an omitted end the same point as the stated start."""
        stated = dict(value)
        start_line = stated.get("start_line", 1)
        end_line = stated.setdefault("end_line", start_line)
        if end_line == start_line and "end_column" not in stated:
            stated["end_column"] = stated.get("start_column", 0)
        return stated

    @model_validator(mode="after")
    def closes_after_it_opens(self) -> Self:
        """Require the end to follow the start in source order."""
        if self.end_line < self.start_line:
            raise ValueError(f"source span ends on line {self.end_line} before {self.start_line}")
        if self.end_line == self.start_line and self.end_column < self.start_column:
            raise ValueError(
                f"source span ends at column {self.end_column} before {self.start_column}"
            )
        return self
