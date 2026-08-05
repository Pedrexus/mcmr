import re
from typing import TYPE_CHECKING

from .clang import ClangTidyOracle

if TYPE_CHECKING:
    from typing import ClassVar

    from ...contracts import Diagnostic


class ClangTidyMagnitudeOracle(ClangTidyOracle):
    """Read the magnitude clang-tidy measured, not only the place it reported.

    A check answering a threshold writes the number it measured inside its own message, so driving
    the threshold to zero and reading that number back makes clang-tidy an oracle for a measurement
    the way Pylint's design messages are.
    """

    tool = "clang-tidy magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"(\d+) \(threshold")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude clang-tidy wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0
