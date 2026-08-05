import re
from typing import TYPE_CHECKING

from .eslint import ESLintOracle

if TYPE_CHECKING:
    from typing import ClassVar

    from ...contracts import Diagnostic


class ESLintMagnitudeOracle(ESLintOracle):
    """Read the magnitude ESLint measured, not only the place it reported.

    A `max-` rule writes the number it counted inside its own message, the way Pylint writes it
    inside a design message, so driving the ceiling to zero and reading that number back makes
    ESLint an oracle for a measurement rather than only for a set of places.
    """

    tool = "eslint magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"\((\d+)\)")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude ESLint wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0
