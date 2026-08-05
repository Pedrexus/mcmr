import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...contracts import Diagnostic
from ..base import Oracle

if TYPE_CHECKING:
    from typing import ClassVar


class ClangTidyOracle(Oracle):
    """Read what clang-tidy reports for a chosen set of its checks, out of its own diagnostics.

    clang-tidy compiles what it reads, so it wants a compilation database naming every translation
    unit and the flags each is built with. Writing that database is part of running the tool at
    all, which is why it lives here rather than in every fixture that wants an answer.
    """

    tool = "clang-tidy"
    binary = "clang-tidy"
    diagnostic: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<path>.+?):(?P<line>\d+):\d+: (?:warning|error): (?P<detail>.*) \[(?P<check>\S+)\]$"
    )
    units: ClassVar[tuple[str, ...]] = (".c", ".cc", ".cpp", ".cxx", ".cu")

    standard: str = "c++23"
    settings: dict[str, str] = {}

    def database(self, root: Path) -> list[Path]:
        """Write the compilation database and return the translation units it names."""
        compiled = sorted(
            path for path in root.rglob("*") if path.suffix in self.units and path.is_file()
        )
        (root / "compile_commands.json").write_text(
            json.dumps(
                [
                    {
                        "directory": str(root.resolve()),
                        "file": str(unit.resolve()),
                        "command": f"clang++ -std={self.standard} -c {unit.resolve()}",
                    }
                    for unit in compiled
                ],
                indent=1,
            )
        )
        return compiled

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic one of the chosen checks produced over one tree."""
        compiled = self.database(root)
        stated = ", ".join(f"{name}: {value}" for name, value in self.settings.items())
        completed = self.ran(
            [
                "clang-tidy",
                "-p",
                ".",
                "--quiet",
                f"--checks=-*,{','.join(self.rules)}",
                f"--config={{CheckOptions: {{{stated}}}}}",
                *(str(unit) for unit in compiled),
            ],
            root,
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=found["path"],
                line=int(found["line"]),
                rule=found["check"],
                detail=found["detail"],
            )
            for line in completed.stdout.splitlines()
            if (found := self.diagnostic.match(line)) is not None
            and wanted.intersection(found["check"].split(","))
        ]
