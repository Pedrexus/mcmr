import json
import os
from typing import TYPE_CHECKING

from httpx import AsyncBaseTransport, AsyncClient, HTTPError, Response
from patos import FrozenModel
from pydantic import Field, InstanceOf, JsonValue, TypeAdapter, ValidationError

from ....domain.contracts import ModelProvenance
from ....domain.primitives import NonEmptyStr
from ...report import JsonReport

if TYPE_CHECKING:
    from collections.abc import Mapping


class OpenRouterClient(FrozenModel):
    """Run one schema-constrained chat completion against an OpenRouter server."""

    server: NonEmptyStr = "https://openrouter.ai/api/v1"
    model: NonEmptyStr = "anthropic/claude-sonnet-5"
    reasoning_effort: NonEmptyStr = "none"
    timeout_seconds: int = Field(default=180, ge=1)
    transport: InstanceOf[AsyncBaseTransport] | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    def answer(self, completion: Mapping[str, JsonValue]) -> str:
        """Read the single structured answer one completion carries."""
        choices = completion.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        choice = JsonReport(document=first if isinstance(first, dict) else {})
        answer = choice.group("message").text("content")
        if not answer:
            raise RuntimeError(f"OpenRouter returned no answer. {json.dumps(completion)[:500]}")
        return answer

    def body(
        self,
        schema_document: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> dict[str, JsonValue]:
        """Build one OpenAI-compatible request that closes the answer schema."""
        body: dict[str, JsonValue] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": dict(schema_document)},
            },
        }
        if self.reasoning_effort != "none":
            body["reasoning"] = {"effort": self.reasoning_effort}
        return body

    def completion(self, response: Response) -> dict[str, JsonValue]:
        """Read one successful completion or state the refusal within a bounded diagnostic."""
        if not response.is_success:
            diagnostic = response.text.strip()[-500:]
            raise RuntimeError(f"OpenRouter responded with {response.status_code}. {diagnostic}")
        return TypeAdapter(dict[str, JsonValue]).validate_json(response.content)

    async def exchange(
        self,
        client: AsyncClient,
        request: dict[str, JsonValue],
        headers: dict[str, str],
    ) -> dict[str, JsonValue]:
        """Post one authorized request and read the completion it answered with."""
        response = await client.post("/chat/completions", headers=headers, json=request)
        return self.completion(response)

    def headers(self) -> dict[str, str]:
        """Read the request key from the environment so no configuration ever holds it."""
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OpenRouter needs the `OPENROUTER_API_KEY` environment variable")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def invoke(
        self,
        schema_document: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one structured completion and return its answer source with its provenance."""
        request = self.body(schema_document, prompt=prompt, name=name)
        headers = self.headers()
        async with AsyncClient(
            base_url=self.server,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            try:
                completion = await self.exchange(client, request, headers)
            except (HTTPError, ValidationError) as error:
                raise RuntimeError(f"OpenRouter could not answer. {error!r}"[:500]) from error
        return self.answer(completion), self.provenance(completion)

    def provenance(self, completion: Mapping[str, JsonValue]) -> ModelProvenance:
        """Turn one completion's reported usage into shared, nonnegative model provenance."""
        report = JsonReport(document=dict(completion))
        usage = report.group("usage")
        return ModelProvenance(
            backend="openrouter",
            model=report.text("model") or self.model,
            reasoning_effort=self.reasoning_effort,
            input_tokens=usage.count("prompt_tokens"),
            cached_input_tokens=usage.group("prompt_tokens_details").count("cached_tokens"),
            output_tokens=usage.count("completion_tokens"),
            reasoning_tokens=usage.group("completion_tokens_details").count("reasoning_tokens"),
        )
