from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt

from ....domain.contracts import Edit, Finding, FixSafety
from ..data.source import SourceReader

if TYPE_CHECKING:
    from ....facts.foundation import SourceSpan
    from ..data.report.check import CheckReport
    from ..data.report.failure import RuleFailure


class CheckRendering(FrozenModel, ABC):
    """Render one check for a terminal in the register a reader requested."""

    limit: NonNegativeInt = 20

    @staticmethod
    def fixable(finding: Finding) -> str:
        """Return the marker for a renderable fix and its safety."""
        if not isinstance(finding.repair, Edit):
            return ""
        return " [*]" if finding.repair.safety is FixSafety.SAFE else " [?]"

    @staticmethod
    def position(span: SourceSpan) -> str:
        """Return the file, line, and column an editor jumps to."""
        return f"{span.path}:{span.start_line}:{span.start_column + 1}"

    @abstractmethod
    def diagnostic(
        self, failure: RuleFailure, finding: Finding, source: SourceReader
    ) -> list[str]:
        """Return the lines one finding of one failure takes in this register."""

    def render(self, projection: CheckReport) -> str:
        """State every failure this view holds, then what the whole run cost."""
        source = SourceReader(root=Path(projection.root))
        diagnostics = [
            (failure, finding) for failure in projection.failures for finding in failure.reported
        ]
        shown = diagnostics[: self.limit]
        total = max(len(diagnostics), projection.failure_count, projection.finding_count)
        omitted = total - len(shown)
        return "\n".join(
            [
                *(
                    line
                    for failure, finding in shown
                    for line in self.diagnostic(failure, finding, source)
                ),
                *([f"and {omitted} more diagnostics"] if omitted else []),
                "",
                f"{projection.file_count} files, {projection.fact_count} facts, "
                f"{projection.rule_execution_count}/{projection.rule_count} rules, "
                f"{projection.skipped_rule_count} skipped, "
                f"{projection.table_query_count} table queries, "
                f"{projection.observation_count} observations, "
                f"{projection.failure_count} failures, "
                f"{projection.finding_count} findings, {projection.unassessed_count} unassessed, "
                f"kernel {projection.kernel_milliseconds:.0f} ms, "
                f"rules {projection.rule_milliseconds:.0f} ms",
            ]
        )
