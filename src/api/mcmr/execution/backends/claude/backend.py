from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, InstanceOf, JsonValue

from ....domain import primitives
from ...contracts import CommandRunner, SubprocessRunner
from ..batched import BatchedBackend
from .harness import ClaudeHarness

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....domain.contracts import ModelProvenance


class ClaudeBackend(BatchedBackend):
    """Run each contextual rule through an isolated single-turn Claude Code process."""

    name: ClassVar[str] = "claude"
    binary: primitives.NonEmptyStr = "claude"
    model: primitives.NonEmptyStr = "claude-sonnet-5"
    reasoning_effort: primitives.NonEmptyStr = "none"
    timeout_seconds: int = Field(default=180, ge=1)
    runner: InstanceOf[CommandRunner] = Field(
        default_factory=SubprocessRunner,
        exclude=True,
        repr=False,
    )

    @cached_property
    def harness(self) -> ClaudeHarness:
        """Build the configured isolated process harness once."""
        return ClaudeHarness.model_validate(self, from_attributes=True)

    async def turn(
        self,
        schema: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one bounded Claude Code process for this schema-constrained prompt."""
        del name
        return await self.harness.invoke(schema, prompt=prompt)


ClaudeBackend.model_rebuild(_types_namespace={"primitives": primitives})
