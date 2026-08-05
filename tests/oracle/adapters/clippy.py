import json
from pathlib import Path

from ..contracts import Diagnostic
from .base import Oracle


class ClippyOracle(Oracle):
    """Read what Clippy reports for a chosen set of its lints, out of the compiler's own JSON.

    The lint that produced a diagnostic is read from its code rather than from its prose, so a
    renamed or retired lint answers with nothing instead of quietly matching a sentence.
    """

    tool = "clippy"
    binary = "cargo"

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic one of the chosen lints produced over one crate."""
        completed = self.ran(
            ["cargo", "clippy", "--offline", "--lib", "--message-format", "json"], root
        )
        wanted = {f"clippy::{name}" for name in self.rules}
        return [
            Diagnostic(
                path=str(root / span["file_name"]),
                line=span["line_start"],
                rule=record["message"]["code"]["code"],
                detail=record["message"]["message"],
            )
            for line in completed.stdout.splitlines()
            if (record := json.loads(line))["reason"] == "compiler-message"
            and (record["message"].get("code") or {}).get("code") in wanted
            for span in record["message"]["spans"][:1]
        ]
