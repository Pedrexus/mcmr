import json
import sys
from importlib.util import find_spec
from pathlib import Path

from ...contracts import Diagnostic
from ..base import Oracle


class PylintOracle(Oracle):
    """Read what Pylint reports for a chosen set of its messages, out of its own JSON report."""

    tool = "pylint"
    binary = "pylint"

    options: list[str] = []

    @classmethod
    def present(cls) -> bool:
        """Whether Pylint is importable, which is how the suite runs it."""
        return find_spec("pylint") is not None

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every message Pylint reported for the chosen symbols."""
        completed = self.ran(
            [
                sys.executable,
                "-m",
                "pylint",
                "--disable=all",
                f"--enable={','.join(self.rules)}",
                "--output-format=json2",
                "--score=n",
                *self.options,
                str(root),
            ]
        )
        report = json.loads(completed.stdout or '{"messages": []}')
        return [
            Diagnostic(
                path=item["absolutePath"],
                line=item["line"],
                rule=item["symbol"],
                detail=item["message"],
            )
            for item in report["messages"]
        ]
