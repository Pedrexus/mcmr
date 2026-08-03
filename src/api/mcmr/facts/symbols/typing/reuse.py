from typing import TYPE_CHECKING

from pydantic import model_validator

from .definition import TypingDefinition

if TYPE_CHECKING:
    from typing import Self

    from ...foundation import SourceSpan


class TypingReuse(TypingDefinition):
    """Locate one typing declaration and every other module importing it."""

    importing_spans: list[SourceSpan] = []

    @model_validator(mode="after")
    def imports_are_distinct_other_modules(self) -> Self:
        """Require every retained import to come from one distinct other module."""
        paths = [span.path for span in self.importing_spans]
        if self.span.path in paths:
            raise ValueError("typing declaration cannot import itself")
        if len(paths) != len(set(paths)):
            raise ValueError("typing reuse repeats an importing module")
        return self
