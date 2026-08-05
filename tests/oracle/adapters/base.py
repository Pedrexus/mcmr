import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel

from mcmr.domain.contracts import RuleValue

from ..contracts.report import Report
from ..contracts.site import Site

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ..contracts.diagnostic import Diagnostic


class Oracle(FrozenModel, ABC):
    """Run one upstream tool over one tree and read its own output back as located findings.

    A tool arrives as a subclass registering itself under the name a rule reference spells, so the
    harness gains one without any comparison learning how that tool is invoked or how it writes
    what it found. Each subclass also owns whatever the tool needs before it will run at all, such
    as the compilation database clang-tidy wants and the flat configuration ESLint wants, since
    that is a fact about the tool rather than about the source either reader is looking at.
    """

    tool: ClassVar[str]
    binary: ClassVar[str]
    oracles: ClassVar[dict[str, type["Oracle"]]] = {}

    rules: list[str] = []

    def __init_subclass__(cls) -> None:
        """Register one adapter under the tool it runs."""
        super().__init_subclass__()
        Oracle.oracles[cls.tool] = cls

    @property
    def name(self) -> str:
        """Return the tool and the rules this adapter asked it for."""
        return " ".join((self.tool, *self.rules))

    @classmethod
    def installed(cls, tool: str) -> bool:
        """Whether the program one registered tool needs can be found here."""
        return cls.oracles[tool].present()

    @classmethod
    def of(cls, tool: str, *rules: str) -> Oracle:
        """Return the adapter for one tool, asking it for exactly these rules."""
        return cls.oracles[tool](rules=rules)

    @classmethod
    def present(cls) -> bool:
        """Whether this tool's program is on the path."""
        return shutil.which(cls.binary) is not None

    @abstractmethod
    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every finding this tool reported, read out of its own output."""

    def located(self, root: Path, path: str, line: int) -> Site:
        """Return one reported location as a path relative to the tree, since a name is not one."""
        return Site.at(Path(path).resolve().relative_to(root.resolve()).as_posix(), line)

    def measured(self, found: Diagnostic) -> int:
        """Return how many findings one diagnostic stands for, which is one for a plain report.

        A tool asked for a magnitude states it once and names the number inside its own message, so
        an adapter reading measurements overrides this and every unit becomes one site. That is
        what makes a measurement compare as a multiset, where a reader measuring eleven against
        twelve would otherwise agree by having reported in the same place.
        """
        return 1

    def ran(
        self, command: Sequence[str], directory: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run one tool, letting a nonzero exit stand since a finding is what causes one.

        A working directory is only ever set by an adapter that needs one, such as Clippy inside
        the crate it builds. Stepping into the tree by default is not harmless: Pylint run from
        inside a package it is reading imports that package's `functools` instead of the standard
        library's and reports nothing at all.
        """
        return subprocess.run(command, capture_output=True, text=True, check=False, cwd=directory)

    def report(self, root: Path) -> Report:
        """Return where this tool reported over one tree."""
        return Report(
            reader=self.name,
            sites=[
                self.located(root, found.path, found.line)
                for found in self.diagnostics(root)
                for _ in range(self.measured(found))
            ],
        )


def scalar_row(row: Mapping[str, RuleValue | None]) -> RuleValue:
    """Return the one populated scalar column from a normalized value row."""
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        if (value := row[name]) is not None:
            return value
    raise TypeError("the rule emitted no scalar value")


def required_row_value[Value: RuleValue](
    row: Mapping[str, RuleValue | None], name: str, expected: type[Value]
) -> Value:
    """Return one required Polars row value after checking its declared scalar type."""
    value = row[name]
    if not isinstance(value, expected):
        raise TypeError(f"{name} must contain {expected.__name__}")
    return value
