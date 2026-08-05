import json
from pathlib import Path

from ..contracts import Diagnostic
from .base import Oracle


class RuffOracle(Oracle):
    """Read what Ruff reports for a chosen set of its codes, out of its own JSON output.

    Suppressions are read past by default. A `# noqa` says what an author decided rather than what
    the reader saw, and comparing two analyses through two suppression systems compares neither.
    """

    tool = "ruff"
    binary = "ruff"

    respect_suppressions: bool = False

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic Ruff reported for the chosen codes."""
        completed = self.ran(
            [
                "ruff",
                "check",
                "--no-cache",
                "--isolated",
                *([] if self.respect_suppressions else ["--ignore-noqa"]),
                "--select",
                ",".join(self.rules),
                "--output-format",
                "json",
                str(root),
            ]
        )
        return [
            Diagnostic(
                path=item["filename"],
                line=item["location"]["row"],
                rule=item["code"] or "",
                detail=item["message"],
            )
            for item in json.loads(completed.stdout or "[]")
        ]
