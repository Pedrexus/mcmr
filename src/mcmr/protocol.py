import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import JsonValue, NonNegativeInt, SkipValidation

from .bases import FrozenFlexModel

if TYPE_CHECKING:
    from collections.abc import Mapping

type KernelArgument = str | bool | list[str]


class KernelStats(FrozenFlexModel):
    """Measure what the kernel did to answer one request."""

    file_count: NonNegativeInt = 0
    byte_count: NonNegativeInt = 0
    fact_count: NonNegativeInt = 0
    parse_failure_count: NonNegativeInt = 0
    discovery_nanoseconds: NonNegativeInt = 0
    extraction_nanoseconds: NonNegativeInt = 0
    graph_nanoseconds: NonNegativeInt = 0
    node_count: NonNegativeInt = 0
    edge_count: NonNegativeInt = 0


class KernelAnswer(FrozenFlexModel):
    """Hold one kernel response as it arrived, before anything inside it is narrowed.

    Only the envelope is checked here. The fact streams and the graph are handed on untouched
    because the models that own them validate them, and walking that payload twice would cost the
    whole repository on every run to learn nothing the second pass does not already learn.
    """

    version: int
    facts: SkipValidation[dict[str, list[JsonValue]]] = {}
    graph: SkipValidation[JsonValue] = None
    stats: KernelStats = KernelStats()


class KernelClient(FrozenFlexModel):
    """Run the analysis kernel over one request and hold it to the protocol this release speaks.

    Every question this package asks the kernel is the same exchange. One JSON request goes in on
    standard input, one JSON response comes back on standard output, and a binary answering for
    another protocol is refused rather than read. Where to look and what to leave out are the same
    for every question, so they belong to the client and the caller states only what it wants.
    """

    protocol: ClassVar[int] = 1

    binary: Path
    root: Path
    exclude: tuple[str, ...] = ()

    def ask(self, request: Mapping[str, KernelArgument]) -> KernelAnswer:
        """Return what the kernel answered to one request, once its protocol version agrees."""
        stated: dict[str, KernelArgument] = {"root": str(self.root), **request}
        if self.exclude:
            stated["exclude"] = list(self.exclude)
        completed = subprocess.run(
            [str(self.binary)],
            input=json.dumps(stated),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"the analysis kernel failed: {completed.stderr.strip()}")
        answer = KernelAnswer.model_validate_json(completed.stdout)
        if answer.version != self.protocol:
            raise RuntimeError(
                f"the analysis kernel speaks protocol {answer.version} "
                f"and this release speaks {self.protocol}"
            )
        return answer
