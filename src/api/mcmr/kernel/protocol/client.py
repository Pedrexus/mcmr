import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel

from .exchange import KernelExchange
from .messages import KernelAnswer, KernelArgument, KernelStats, KernelStreamBatch

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class KernelClient(FrozenModel):
    """Run the analysis kernel under the protocol this release speaks."""

    protocol: ClassVar[int] = 22

    binary: Path
    root: Path

    def ask(self, request: Mapping[str, KernelArgument]) -> KernelAnswer:
        """Return what the kernel answered once its protocol version agrees."""
        stated: dict[str, KernelArgument] = {"root": str(self.root), **request}
        return self._validated_answer(self._run(stated))

    def stream(
        self, request: Mapping[str, KernelArgument]
    ) -> Iterator[KernelStreamBatch | KernelStats]:
        """Yield independently serialized families and then completed statistics."""
        stated: dict[str, KernelArgument] = {"root": str(self.root), **request, "stream": True}
        return KernelExchange(self.binary, stated, self.protocol).read()

    def _run(self, stated: Mapping[str, KernelArgument]) -> subprocess.CompletedProcess[str]:
        """Run one buffered exchange and retain its complete process result."""
        return subprocess.run(
            [str(self.binary)],
            input=json.dumps(stated),
            capture_output=True,
            text=True,
            check=False,
        )

    def _validated_answer(self, completed: subprocess.CompletedProcess[str]) -> KernelAnswer:
        """Validate one successful buffered response and its protocol version."""
        if completed.returncode:
            raise RuntimeError(f"the analysis kernel failed: {completed.stderr.strip()}")
        answer = KernelAnswer.model_validate_json(completed.stdout)
        if answer.version != self.protocol:
            raise RuntimeError(
                f"the analysis kernel speaks protocol {answer.version} "
                f"and this release speaks {self.protocol}"
            )
        return answer
