from typing import Annotated

from patos import FrozenModel
from pydantic import Field, NonNegativeFloat

from .result import ContextualSweepResult


class ContextualSweepReport(FrozenModel):
    """Summarize one live pass through every contextual rule contract."""

    results: Annotated[list[ContextualSweepResult], Field(min_length=1)]
    elapsed_seconds: NonNegativeFloat

    @property
    def cached_input_tokens(self) -> int:
        """Return cached input tokens reported once per isolated rule turn."""
        return sum(item.provenance.cached_input_tokens for item in self.results)

    @property
    def error_count(self) -> int:
        """Return isolated backend turns that failed their output contract."""
        return sum(bool(item.error) for item in self.results)

    @property
    def input_tokens(self) -> int:
        """Return input tokens reported once per isolated rule turn."""
        return sum(item.provenance.input_tokens for item in self.results)

    @property
    def message_characters(self) -> int:
        """Return retained explanation characters across every contextual rule."""
        return sum(len(message) for item in self.results for message in item.messages)

    @property
    def output_tokens(self) -> int:
        """Return output tokens reported once per isolated rule turn."""
        return sum(item.provenance.output_tokens for item in self.results)

    @property
    def reasoning_tokens(self) -> int:
        """Return reasoning tokens reported once per isolated rule turn."""
        return sum(item.provenance.reasoning_tokens for item in self.results)
