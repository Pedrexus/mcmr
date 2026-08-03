from typing import TYPE_CHECKING

from ...accounting.upstream import Coverage, CoverageEntry, ToolCoverage
from ..interface import console, readable_table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.table import Table as RichTable


class CoveragePresentation:
    """Render filtered upstream coverage as a summary or one detailed inventory."""

    def __init__(self, *, group: str, state: str, limit: int) -> None:
        self.group = group
        self.state = state
        self.limit = limit

    def show(self, reports: Sequence[ToolCoverage]) -> None:
        """Choose the compact multi-tool summary or the one-tool detail table."""
        if len(reports) > 1:
            self._summary(reports)
            return
        self._detail(reports[0])

    @staticmethod
    def _headings() -> dict[Coverage, str]:
        """Map coverage states to compact table headings."""
        return {
            Coverage.NATIVE: "Nat",
            Coverage.DELEGATED: "Del",
            Coverage.ADAPTED: "Adp",
            Coverage.INAPPLICABLE: "N/A",
            Coverage.UNAVAILABLE: "Gap",
        }

    def _detail(self, report: ToolCoverage) -> None:
        """Render every filtered upstream rule for one tool."""
        entries = self._entries(report)
        languages = ", ".join(language.value for language in report.profile.languages)
        table = readable_table(
            title=f"MCMR against {report.profile.name} for {languages}, {len(entries)} rules"
        )
        for column in ("Rule", "Group", "State", "Answered by"):
            table.add_column(column)
        for entry in entries[: self.limit or len(entries)]:
            table.add_row(
                " ".join(word for word in (entry.rule.code, entry.rule.symbol) if word),
                entry.rule.group,
                entry.coverage,
                ", ".join(entry.rules),
            )
        console.print(table)
        tally = report.tally()
        console.print(
            " ".join(f"{state}={count}" for state, count in tally.items())
            + f", {sum(tally.values())} accounted for",
            soft_wrap=True,
        )

    def _entries(self, report: ToolCoverage) -> list[CoverageEntry]:
        """Return upstream entries matching the requested group and state fragments."""
        return [
            entry
            for entry in report.entries
            if self.group in entry.rule.group and self.state in entry.coverage
        ]

    def _summary(self, reports: Sequence[ToolCoverage]) -> None:
        """Render one aggregate row per inventoried tool."""
        table = readable_table(f"MCMR coverage across {len(reports)} upstream tools")
        table.caption = "Nat native  Del delegated  Adp adapted  N/A inapplicable  Gap unavailable"
        for column in ("Tool", "Languages", "Rules"):
            table.add_column(column, justify="right" if column == "Rules" else "default")
        for heading in self._headings().values():
            table.add_column(heading, justify="right")
        totals = {coverage_state: 0 for coverage_state in Coverage}
        rule_total = 0
        for report in reports:
            count, tally = self._summary_row(table, report)
            rule_total += count
            for coverage_state, amount in tally.items():
                totals[coverage_state] += amount
        table.add_section()
        table.add_row(
            "Total",
            "",
            f"{rule_total:,}",
            *(f"{totals[coverage_state]:,}" for coverage_state in Coverage),
            style="bold",
        )
        console.print(table, f"{rule_total:,} upstream rules accounted for", soft_wrap=True)

    def _summary_row(
        self,
        table: RichTable,
        report: ToolCoverage,
    ) -> tuple[int, dict[Coverage, int]]:
        """Append one tool summary and return its filtered counts."""
        entries = self._entries(report)
        tally = {
            coverage_state: sum(entry.coverage is coverage_state for entry in entries)
            for coverage_state in Coverage
        }
        table.add_row(
            report.profile.name,
            ", ".join(language.value for language in report.profile.languages),
            f"{len(entries):,}",
            *(f"{tally[coverage_state]:,}" for coverage_state in Coverage),
        )
        return len(entries), tally
