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


class CodexHarness(FrozenModel):
    """Run one isolated schema-constrained Codex process."""

    binary: NonEmptyStr = "codex"
    model: NonEmptyStr = "gpt-5.6-sol"
    reasoning_effort: NonEmptyStr = "low"
    timeout_seconds: int = Field(default=180, ge=1)
    runner: InstanceOf[CommandRunner] = Field(
        default_factory=SubprocessRunner,
        exclude=True,
        repr=False,
    )

    def command(self, workspace: Path, *, schema: Path, output: Path) -> list[str]:
        """Build one stateless read-only `codex exec` command."""
        command = [self.binary, "exec", "--model", self.model]
        command += ["--sandbox", "read-only", "--cd", str(workspace)]
        command += ["--skip-git-repo-check", "--ephemeral", "--ignore-user-config"]
        command += ["--ignore-rules", "--output-schema", str(schema)]
        command += ["--output-last-message", str(output), "--json", "--color", "never"]
        command += ["--config", f'model_reasoning_effort="{self.reasoning_effort}"', "-"]
        return command

    async def invoke(
        self,
        schema_document: Mapping[str, JsonValue],
        *,
        prompt: str,
        name: str,
    ) -> tuple[str, ModelProvenance]:
        """Run one isolated Codex turn and return its validated-output source."""
        with TemporaryDirectory(prefix="mcmr-codex-") as directory:
            workspace = Path(directory)
            schema = workspace / f"{name}.schema.json"
            output = workspace / f"{name}.json"
            schema.write_text(json.dumps(schema_document, sort_keys=True))
            result = await self.runner(
                self.command(workspace, schema=schema, output=output),
                prompt,
                workspace,
                self.timeout_seconds,
            )
            self._ensure_success(result)
            return output.read_text(), self.provenance(result)

    def provenance(self, result: CommandResult) -> ModelProvenance:
        """Turn one harness event stream into shared, nonnegative model provenance."""
        input_tokens, cached_tokens, output_tokens, reasoning_tokens, stated_model = self.usage(
            result.stdout
        )
        return ModelProvenance(
            backend="codex",
            model=stated_model or self.model,
            reasoning_effort=self.reasoning_effort,
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def usage(self, stdout: str) -> tuple[int, int, int, int, str]:
        """Read token counts and reported model from the final Codex event."""
        completed = JsonReport(document=self._completed_event(stdout))
        usage = completed.group("usage")
        return (
            usage.count("input_tokens"),
            usage.count("cached_input_tokens"),
            usage.count("output_tokens"),
            usage.count("reasoning_output_tokens"),
            completed.text("model"),
        )

    @staticmethod
    def _completed_event(stdout: str) -> dict[str, JsonValue]:
        adapter = TypeAdapter(dict[str, JsonValue])
        records = [adapter.validate_json(line) for line in stdout.splitlines() if line.strip()]
        return next(
            (record for record in reversed(records) if record.get("type") == "turn.completed"),
            {},
        )

    @staticmethod
    def _ensure_success(result: CommandResult) -> None:
        if not result.returncode:
            return
        diagnostic = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Codex harness exited with {result.returncode}. {diagnostic[-500:]}")
