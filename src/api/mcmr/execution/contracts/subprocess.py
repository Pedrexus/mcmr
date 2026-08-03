import asyncio
import os
import signal
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from patos import FrozenModel

from ...domain.primitives import NonEmptyStr

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class _SubprocessContracts:
    """Own bounded command execution and its replaceable runner contract."""

    class Result(FrozenModel):
        """Retain one bounded harness process result."""

        returncode: int
        stdout: str = ""
        stderr: str = ""

    @runtime_checkable
    class Runner(Protocol):
        """Run one harness command with its prompt on standard input."""

        async def __call__(
            self,
            command: Sequence[str],
            prompt: str,
            cwd: Path,
            timeout_seconds: int,
        ) -> _SubprocessContracts.Result: ...

    class Subprocess(FrozenModel):
        """Run a bounded subprocess without occupying an event-loop worker thread."""

        encoding: NonEmptyStr = "utf-8"

        async def __call__(
            self,
            command: Sequence[str],
            prompt: str,
            cwd: Path,
            timeout_seconds: int,
        ) -> _SubprocessContracts.Result:
            """Capture one shell-free command and stop its process group on expiry."""
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await self._communicate(process, prompt, timeout_seconds)
            except TimeoutError as failure:
                raise await self._timeout(process, failure) from None
            return _SubprocessContracts.Result(
                returncode=process.returncode or 0,
                stdout=stdout.decode(self.encoding, errors="replace"),
                stderr=stderr.decode(self.encoding, errors="replace"),
            )

        @staticmethod
        async def terminate(process: asyncio.subprocess.Process) -> None:
            """Stop and reap one process group, tolerating boundary completion."""
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()

        async def _communicate(
            self,
            process: asyncio.subprocess.Process,
            prompt: str,
            timeout_seconds: int,
        ) -> tuple[bytes, bytes]:
            """Exchange one prompt within its declared timeout."""
            async with asyncio.timeout(timeout_seconds):
                return await process.communicate(prompt.encode(self.encoding))

        async def _timeout(
            self,
            process: asyncio.subprocess.Process,
            failure: TimeoutError,
        ) -> TimeoutError:
            """Terminate one expired process and preserve its timeout."""
            await self.terminate(process)
            return failure


CommandResult = _SubprocessContracts.Result
CommandRunner = _SubprocessContracts.Runner
SubprocessRunner = _SubprocessContracts.Subprocess
