import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import Field, InstanceOf, JsonValue, TypeAdapter

from ....domain.contracts import ModelProvenance
from ....domain.primitives import NonEmptyStr
from ...contracts import CommandResult, CommandRunner, SubprocessRunner
from ...report import JsonReport

if TYPE_CHECKING:
    from collections.abc import Mapping


class ClaudeHarness(FrozenModel):
    """Run one isolated schema-constrained Claude Code process."""

    binary: NonEmptyStr = "claude"
    model: NonEmptyStr = "claude-sonnet-5"
    reasoning_effort: NonEmptyStr = "none"
    timeout_seconds: int = Field(default=180, ge=1)
    runner: InstanceOf[CommandRunner] = Field(
        default_factory=SubprocessRunner,
        exclude=True,
        repr=False,
    )

    @staticmethod
    def answering(billed: JsonReport) -> str:
        """Name the one billed model that answered, leaving a tie or an empty report unnamed."""
        ranked = sorted(
            ((billed.group(name).count("outputTokens"), name) for name in billed.names()),
            reverse=True,
        )
        if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
            return ""
        return ranked[0][1]

    def answer(self, turn: Mapping[str, JsonValue]) -> str:
        """Read the schema-validated answer one turn carries."""
        structured = turn.get("structured_output")
        if structured is not None:
            return json.dumps(structured, sort_keys=True)
        result = turn.get("result")
        if isinstance(result, str) and result.strip():
            return result
        raise RuntimeError(f"Claude returned no structured answer. {json.dumps(turn)[-500:]}")

    def command(self, schema_document: Mapping[str, JsonValue]) -> list[str]:
        """Build one stateless single-turn `claude --print` command."""
        command = [self.binary, "--print", "--model", self.model]
        command += ["--output-format", "json"]
        command += ["--json-schema", json.dumps(schema_document, sort_keys=True)]
        command += ["--tools", "", "--strict-mcp-config"]
        command += ["--safe-mode", "--no-session-persistence"]
        if self.reasoning_effort != "none":
            command += ["--effort", self.reasoning_effort]
        return command

    async def invoke(
        self,
        schema_document: Mapping[str, JsonValue],
        *,
        prompt: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one isolated Claude turn and return its structured-output source."""
        with TemporaryDirectory(prefix="mcmr-claude-") as directory:
            result = await self.runner(
                self.command(schema_document),
                prompt,
                Path(directory),
                self.timeout_seconds,
            )
        self._ensure_success(result)
        turn = self.turn(result.stdout)
        return self.answer(turn), self.provenance(turn)

    def provenance(self, turn: Mapping[str, JsonValue]) -> ModelProvenance:
        """Turn one reported Claude result into shared, nonnegative model provenance.

        A session bills side models such as the safety classifier beside the model that answers,
        so provenance follows the billed entry that produced the most output tokens and reads its
        own counts. Only a turn that billed nothing nameable falls back to the session aggregate.
        """
        report = JsonReport(document=dict(turn))
        billed = report.group("modelUsage")
        answering = self.answering(billed)
        usage = billed.group(answering) if answering else report.group("usage")
        input_name, cached_name, output_name = (
            ("inputTokens", "cacheReadInputTokens", "outputTokens")
            if answering
            else ("input_tokens", "cache_read_input_tokens", "output_tokens")
        )
        return ModelProvenance(
            backend="claude",
            model=answering or self.model,
            reasoning_effort=self.reasoning_effort,
            input_tokens=usage.count(input_name),
            cached_input_tokens=usage.count(cached_name),
            output_tokens=usage.count(output_name),
        )

    def turn(self, stdout: str) -> dict[str, JsonValue]:
        """Read the single JSON result object one printed turn emits."""
        turn = TypeAdapter(dict[str, JsonValue]).validate_json(stdout)
        if turn.get("is_error"):
            raise RuntimeError(f"Claude reported a failed turn. {json.dumps(turn)[-500:]}")
        return turn

    @staticmethod
    def _ensure_success(result: CommandResult) -> None:
        if not result.returncode:
            return
        diagnostic = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Claude harness exited with {result.returncode}. {diagnostic[-500:]}")
