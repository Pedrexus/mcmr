from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from .data.source import SourceReader
from .diagnostic import DiagnosticRenderer
from .summary import SummaryRenderer

if TYPE_CHECKING:
    from ...domain.contracts import Finding
    from .data.report import CheckReport, RuleFailure


class RichCheck(FrozenModel):
    """Render a check as navigable Rich summaries and detailed finding panels."""

    limit: NonNegativeInt = 20

    def render(self, projection: CheckReport) -> Group:
        """Return the run summary followed by retained findings."""
        source = SourceReader(root=Path(projection.root))
        diagnostics = DiagnosticRenderer(source=source)
        summary = SummaryRenderer(projection=projection)
        details = self._details(projection, diagnostics)
        return Group(summary.summary(), summary.execution(), *details)

    @staticmethod
    def _finish_details(details: list[Panel], omitted: int) -> list[Panel]:
        """Append the omitted count or the successful empty state."""
        if omitted:
            details.append(RichCheck._omitted_panel(omitted))
        if not details:
            details.append(RichCheck._success_panel())
        return details

    @staticmethod
    def _omitted_panel(omitted: int) -> Panel:
        """Return the count of diagnostics outside the current view."""
        message = Text(f"{omitted} more diagnostics are outside this view", style="yellow")
        return Panel(message, border_style="yellow")

    @staticmethod
    def _success_panel() -> Panel:
        """Return the successful empty result panel."""
        return Panel(Text("No policy failures", style="bold green"), border_style="green")

    def _details(
        self,
        projection: CheckReport,
        renderer: DiagnosticRenderer,
    ) -> list[Panel]:
        """Render findings up to the configured display limit."""
        diagnostics: list[tuple[RuleFailure, Finding]] = [
            (failure, finding) for failure in projection.failures for finding in failure.reported
        ]
        details = [renderer.render(*item) for item in diagnostics[: self.limit]]
        return self._finish_details(details, len(diagnostics) - len(details))
