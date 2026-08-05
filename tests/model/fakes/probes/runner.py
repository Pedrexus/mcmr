import json
from pathlib import Path
from typing import TYPE_CHECKING

from anyio import Path as AsyncPath
from anyio import sleep
from pydantic import JsonValue, TypeAdapter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.execution import CommandResult


class StubRunner:
    """Answer one controlled harness command and retain the invocation for inspection."""

    def __init__(
        self,
        payload: dict[str, JsonValue] | None,
        result: CommandResult,
        delay_seconds: float = 0.0,
    ) -> None:
        self.payload = payload
        self.result = result
        self.delay_seconds = delay_seconds
        self.active = 0
        self.maximum_active = 0
        self.calls: list[tuple[list[str], str, Path, int]] = []
        self.schema: dict[str, JsonValue] | None = None

    async def __call__(
        self,
        command: list[str],
        prompt: str,
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        """Answer where the command asked, through its files or on standard output."""
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.calls.append((command, prompt, cwd, timeout_seconds))
        await sleep(self.delay_seconds)
        if "--output-schema" in command:
            await self.exchange(command)
        self.active -= 1
        return self.result

    async def exchange(self, command: Sequence[str]) -> None:
        """Read the schema a file-based harness wrote and answer in the file it named."""
        schema = Path(command[command.index("--output-schema") + 1])
        self.schema = TypeAdapter(dict[str, JsonValue]).validate_json(
            await AsyncPath(schema).read_text()
        )
        if self.payload is not None:
            output = Path(command[command.index("--output-last-message") + 1])
            await AsyncPath(output).write_text(json.dumps(self.payload))

    def flag(self, name: str, index: int = 0) -> str:
        """Read the value one recorded command passed after a named flag."""
        command = self.calls[index][0]
        return command[command.index(name) + 1]
