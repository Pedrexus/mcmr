from typing import TYPE_CHECKING, Annotated, Literal

from patos import FrozenModel
from pydantic import Field, field_validator

from .case import ContextualCase

if TYPE_CHECKING:
    from pathlib import Path


class ContextualCorpus(FrozenModel):
    """Hold a versioned, manually reviewed contextual evaluation corpus."""

    schema_version: Literal[1] = 1
    cases: Annotated[list[ContextualCase], Field(min_length=1)]

    @classmethod
    def read(cls, path: Path) -> ContextualCorpus:
        """Read one explicitly named corpus without retaining any runtime state."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    @field_validator("cases")
    @classmethod
    def unique_cases(cls, cases: list[ContextualCase]) -> list[ContextualCase]:
        """Keep every rule and case name pair unique for stable comparisons."""
        identities = [(case.rule, case.name) for case in cases]
        if len(identities) != len(set(identities)):
            raise ValueError("contextual case names must be unique within each rule")
        return cases

    def grouped(self) -> dict[str, list[ContextualCase]]:
        """Return cases in file order under each rule identifier."""
        grouped: dict[str, list[ContextualCase]] = {}
        for case in self.cases:
            grouped.setdefault(case.rule, []).append(case)
        return grouped
