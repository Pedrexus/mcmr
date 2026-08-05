import re
from typing import TYPE_CHECKING

from .pylint import PylintOracle

if TYPE_CHECKING:
    from typing import ClassVar

    from ...contracts import Diagnostic


class PylintMagnitudeOracle(PylintOracle):
    """Read the magnitude Pylint measured, not only the place it reported.

    Pylint writes `(12/0)` inside every design message, which is what makes it an oracle for a
    measurement rather than only for a set of places. `options` drives the ceiling to zero so
    nothing is filtered out.
    """

    tool = "pylint magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"\((\d+)/\d+\)")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude Pylint wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0
