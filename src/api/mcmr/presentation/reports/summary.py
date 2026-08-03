from patos import FrozenModel
from pydantic import InstanceOf
from rich import box
from rich.table import Table
from rich.text import Text

from .data.report import CheckReport


class SummaryRenderer(FrozenModel):
    """Render the totals and execution lanes of one check report."""

    projection: InstanceOf[CheckReport]

    def execution(self) -> Table:
        """Show how many repository-wide queries each fact family executes."""
        table = self._execution_table()
        self._lane_rows(table)
        if self.projection.rule_counts_by_lane and self.projection.table_queries_by_family:
            table.add_section()
        self._query_rows(table)
        return table

    def summary(self) -> Table:
        """Return the compact run totals that orient detailed results."""
        table = self._summary_table()
        timings = self._timings()
        for index, (label, count) in enumerate(self._counts()):
            timing, elapsed = timings[index] if index < len(timings) else ("", 0.0)
            table.add_row(label, count, timing, f"{elapsed:.0f} ms" if timing else "")
        return table

    @staticmethod
    def _execution_columns(table: Table) -> None:
        """Declare columns used by execution lane rows."""
        table.add_column("Work")
        table.add_column("Kind")
        table.add_column("Runs", justify="right")

    @staticmethod
    def _summary_columns(table: Table) -> None:
        """Declare columns used by summary rows."""
        table.add_column("Analysis")
        table.add_column("Count", justify="right")
        table.add_column("Timing")
        table.add_column("Elapsed", justify="right")

    @staticmethod
    def _table(title: str, caption: str | None = None) -> Table:
        """Create the shared report table shell."""
        return Table(
            title=title,
            caption=caption,
            box=box.SIMPLE_HEAD,
            header_style="bold cyan",
            row_styles=("", "dim"),
            min_width=60,
        )

    def _analysis_counts(self) -> list[tuple[str, str | Text]]:
        """Return repository and execution counts."""
        return [
            ("Files", str(self.projection.file_count)),
            ("Facts", str(self.projection.fact_count)),
            ("Rules", f"{self.projection.rule_execution_count}/{self.projection.rule_count}"),
            ("Skipped", str(self.projection.skipped_rule_count)),
            ("Table queries", str(self.projection.table_query_count)),
        ]

    def _caption(self) -> str:
        """Return the complete compact outcome caption."""
        return (
            f"{self.projection.file_count} files, {self.projection.failure_count} failures, "
            f"{self.projection.finding_count} findings, "
            f"{self.projection.unassessed_count} unassessed, "
            f"{self.projection.skipped_rule_count} skipped"
        )

    def _counts(self) -> list[tuple[str, str | Text]]:
        """Return every summary count in display order."""
        return self._analysis_counts() + self._outcome_counts()

    def _execution_table(self) -> Table:
        """Create the execution lane table shell."""
        table = self._table("Execution lanes")
        self._execution_columns(table)
        return table

    def _lane_rows(self, table: Table) -> None:
        """Append contextual and deterministic execution lanes."""
        for lane, count in self.projection.rule_counts_by_lane.items():
            executed = self.projection.rule_executions_by_lane.get(lane, 0)
            table.add_row(lane, "rules", f"{executed}/{count}")

    def _outcome_counts(self) -> list[tuple[str, str | Text]]:
        """Return observation and policy outcome counts."""
        style = "bold red" if self.projection.failure_count else "bold green"
        return [
            ("Observations", str(self.projection.observation_count)),
            ("Failures", Text(str(self.projection.failure_count), style=style)),
            ("Findings", str(self.projection.finding_count)),
            ("Unassessed", str(self.projection.unassessed_count)),
        ]

    def _query_rows(self, table: Table) -> None:
        """Append one row for each queried fact family."""
        for family, count in sorted(self.projection.table_queries_by_family.items()):
            table.add_row(family, "table query", str(count))

    def _summary_table(self) -> Table:
        """Create the check summary table shell."""
        table = self._table("MCMR check", self._caption())
        self._summary_columns(table)
        return table

    def _timings(self) -> list[tuple[str, float]]:
        """Return kernel, rule, and complete elapsed times."""
        kernel = self.projection.kernel_milliseconds
        rules = self.projection.rule_milliseconds
        return [("Kernel", kernel), ("Rules", rules), ("Total", kernel + rules)]
