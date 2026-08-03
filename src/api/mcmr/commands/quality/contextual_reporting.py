import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..interface import console, readable_table

if TYPE_CHECKING:
    from rich.table import Table as RichTable

    from ...contextual.evaluation import ContextualExperimentReport, ContextualSweepReport


class ContextualPresentation:
    """Render one contextual experiment or sweep and optionally persist its report."""

    def __init__(self, output: Path | None) -> None:
        self.output = output

    def experiment(self, report: ContextualExperimentReport) -> None:
        """Show profile accuracy, costs, and the smallest exact choice per rule."""
        console.print(self._experiment_table(report), self._recommendations(report))
        if self.output is not None:
            rendered = report.model_dump(mode="json") | {
                "recommendations": report.recommendations,
                "unresolved": report.unresolved,
            }
            self.output.write_text(
                json.dumps(rendered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def sweep(self, report: ContextualSweepReport) -> None:
        """Show every contextual rule result and aggregate model telemetry."""
        table = readable_table("MCMR contextual sweep")
        for column in ("Rule", "Value", "Findings", "Model"):
            table.add_column(column, justify="right" if column == "Findings" else "default")
        for result in report.results:
            table.add_row(
                result.rule,
                "error" if result.error else result.value,
                str(result.finding_count),
                result.provenance.model,
            )
        console.print(
            table,
            f"{len(report.results)} rules in {report.elapsed_seconds:.1f}s, "
            f"{report.input_tokens} input tokens, {report.cached_input_tokens} cached, "
            f"{report.output_tokens} output tokens, {report.reasoning_tokens} reasoning tokens, "
            f"{report.message_characters} explanation characters, {report.error_count} errors",
            soft_wrap=True,
        )
        if self.output is not None:
            self.output.write_text(
                report.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )

    @staticmethod
    def _experiment_table(report: ContextualExperimentReport) -> RichTable:
        """Build the profile accuracy and telemetry table."""
        table = readable_table("MCMR contextual experiment")
        for column in (
            "Profile",
            "Exact",
            "Accuracy",
            "Time",
            "Input",
            "Cached",
            "Output",
            "Reason",
            "Text",
            "Errors",
        ):
            table.add_column(column, justify="right" if column != "Profile" else "default")
        for result in report.profiles:
            table.add_row(
                result.profile.name,
                f"{result.passed}/{len(result.trials)}",
                f"{result.accuracy:.1f}%",
                f"{result.elapsed_seconds:.1f}s",
                str(result.input_tokens),
                str(result.cached_input_tokens),
                str(result.output_tokens),
                str(result.reasoning_tokens),
                str(result.reasoning_characters),
                str(sum(bool(trial.error) for trial in result.trials)),
            )
        return table

    @staticmethod
    def _recommendations(report: ContextualExperimentReport) -> RichTable:
        """Build the smallest exact backend choice for each contextual rule."""
        table = readable_table("Smallest exact profile by rule")
        for column in ("Rule", "Profile"):
            table.add_column(column)
        for rule, profile in report.recommendations.items():
            table.add_row(rule, profile)
        for rule in report.unresolved:
            table.add_row(rule, "unresolved")
        return table
