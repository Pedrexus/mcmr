from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from httpx import AsyncBaseTransport
from pydantic import Field, InstanceOf, JsonValue

from ....domain import primitives
from ..batched import BatchedBackend
from .client import OpenRouterClient

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....domain.contracts import ModelProvenance


class OpenRouterBackend(BatchedBackend):
    """Run each contextual rule through one schema-constrained OpenRouter completion."""

    name: ClassVar[str] = "openrouter"
    server: primitives.NonEmptyStr = "https://openrouter.ai/api/v1"
    model: primitives.NonEmptyStr = "anthropic/claude-sonnet-5"
    reasoning_effort: primitives.NonEmptyStr = "none"
    timeout_seconds: int = Field(default=180, ge=1)
    transport: InstanceOf[AsyncBaseTransport] | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    @cached_property
    def client(self) -> OpenRouterClient:
        """Build the configured request client once."""
        return OpenRouterClient.model_validate(self, from_attributes=True)

    async def turn(
        self,
        schema: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one bounded HTTP completion for this schema-constrained prompt."""
        return await self.client.invoke(schema, prompt=prompt, name=name)


OpenRouterBackend.model_rebuild(_types_namespace={"primitives": primitives})
