from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, InstanceOf, JsonValue

from ....domain import primitives
from ...contracts import CommandRunner, SubprocessRunner
from ..batched import BatchedBackend
from .harness import CodexHarness

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....domain.contracts import ModelProvenance


class CodexBackend(BatchedBackend):
    """Run each contextual rule through an isolated schema-constrained Codex process."""

    name: ClassVar[str] = "codex"
    binary: primitives.NonEmptyStr = "codex"
    model: primitives.NonEmptyStr = "gpt-5.6-sol"
    reasoning_effort: primitives.NonEmptyStr = "low"
    timeout_seconds: int = Field(default=180, ge=1)
    runner: InstanceOf[CommandRunner] = Field(
        default_factory=SubprocessRunner,
        exclude=True,
        repr=False,
    )

    @cached_property
    def harness(self) -> CodexHarness:
        """Build the configured isolated process harness once."""
        return CodexHarness.model_validate(self, from_attributes=True)

    async def turn(
        self,
        schema: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one bounded Codex process for this schema-constrained prompt."""
        return await self.harness.invoke(schema, prompt=prompt, name=name)


CodexBackend.model_rebuild(_types_namespace={"primitives": primitives})
