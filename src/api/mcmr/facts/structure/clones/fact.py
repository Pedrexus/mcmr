from typing import TYPE_CHECKING

from pydantic import Field, PositiveInt, model_validator

from ...foundation import DetectableCloneTokenCount, Fact

if TYPE_CHECKING:
    from typing import Annotated, Self

    from .fragment import CloneFragment


class CloneGroupFact(Fact):
    """Describe one group of structurally similar source fragments."""

    fragments: Annotated[list[CloneFragment], Field(min_length=2)]
    token_length: DetectableCloneTokenCount
    repository_line_count: PositiveInt

    @property
    def copy_count(self) -> int:
        """Return how many places state this fragment."""
        return len(self.fragments)

    @property
    def line_count(self) -> int:
        """Return the lines one copy covers using the tightest copy."""
        return min(fragment.line_count for fragment in self.fragments)

    @property
    def redundant_line_count(self) -> int:
        """Return lines existing only because this fragment was copied."""
        return self.line_count * (self.copy_count - 1)

    @model_validator(mode="after")
    def fit_inside_repository(self) -> Self:
        """Require distinct nonoverlapping copies fitting inside the repository."""
        by_path: dict[str, list[CloneFragment]] = {}
        for fragment in self.fragments:
            by_path.setdefault(fragment.path, []).append(fragment)
        for path, fragments in by_path.items():
            ordered = sorted(fragments, key=lambda item: (item.start_line, item.end_line))
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if current.start_line <= previous.end_line:
                    raise ValueError(
                        f"clone fragments overlap in {path} at lines "
                        f"{previous.start_line} to {current.end_line}"
                    )
        if self.redundant_line_count > self.repository_line_count:
            raise ValueError(
                f"clone group repeats {self.redundant_line_count} lines inside a repository "
                f"holding {self.repository_line_count}"
            )
        return self
