import xml.etree.ElementTree as ElementTree
from pathlib import Path

from ...contracts import Diagnostic
from ..base import Oracle


class CppcheckOracle(Oracle):
    """Read what Cppcheck reports for a chosen set of its error identifiers, out of its XML report.

    Cppcheck writes its findings to standard error as XML naming the identifier and every location
    a finding spans. The first location is the place it points at and the rest are the supporting
    sites a reader is sent to afterwards, so each of them is one located finding here.
    """

    tool = "cppcheck"
    binary = "cppcheck"

    standard: str = "c++20"

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every finding one of the chosen identifiers produced over one tree."""
        completed = self.ran(
            [
                "cppcheck",
                "--enable=all",
                "--inline-suppr",
                "--quiet",
                "--xml",
                f"--std={self.standard}",
                str(root),
            ]
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=str(root / found.attrib["file"]),
                line=int(found.attrib["line"]),
                rule=error.attrib["id"],
                detail=error.attrib.get("msg", ""),
            )
            for error in ElementTree.fromstring(completed.stderr).iter("error")
            if error.attrib.get("id") in wanted
            for found in error.iter("location")
            if "file" in found.attrib
        ]
