from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import InstanceOf
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ...domain.contracts import Edit, Finding, FixSafety
from .data.source import SourceReader
from .text import CheckRendering

if TYPE_CHECKING:
    from ...domain.contracts import ModelProvenance
    from .data.report import RuleFailure


class DiagnosticRenderer(FrozenModel):
    """Render detailed findings against one repository source reader."""

    source: InstanceOf[SourceReader]

    def render(self, failure: RuleFailure, finding: Finding) -> Panel:
        """Return one detailed source finding panel."""
        facts = self._facts(failure, finding)
        content = self._content(finding, facts)
        title = Text(self._title(failure, finding), style="bold")
        border = "yellow" if isinstance(finding.repair, Edit) else "red"
        return Panel(content, title=title, title_align="left", border_style=border)

    @staticmethod
    def _add_evidence(facts: Table, finding: Finding) -> None:
        """Append retained evidence when present."""
        if finding.evidence:
            facts.add_row("Evidence", "\n".join(finding.evidence))

    @staticmethod
    def _add_measurements(facts: Table, finding: Finding) -> None:
        """Append named measurements when present."""
        if finding.measurements:
            rendered = ", ".join(item.rendered for item in finding.measurements)
            facts.add_row("Measured", rendered)

    @staticmethod
    def _add_provenance(facts: Table, finding: Finding) -> None:
        """Append contextual model provenance when present."""
        if finding.provenance is None:
            return
        provenance = finding.provenance
        facts.add_row("Model", DiagnosticRenderer._model(provenance))
        facts.add_row("Tokens", DiagnosticRenderer._tokens(provenance))

    @staticmethod
    def _add_repair(facts: Table, finding: Finding) -> None:
        """Append the proposed edit or decision when present."""
        if finding.repair is None:
            return
        safety = ""
        if isinstance(finding.repair, Edit):
            safety = "safe" if finding.repair.safety is FixSafety.SAFE else "review"
        label = f"{safety} fix" if safety else "Decision"
        facts.add_row(label.title(), finding.repair.summary)

    @staticmethod
    def _base_facts(failure: RuleFailure, finding: Finding) -> Table:
        """Create the identity and policy rows shared by every finding."""
        facts = Table.grid(padding=(0, 1))
        facts.add_column(style="bold cyan", no_wrap=True)
        facts.add_column()
        facts.add_row("Location", CheckRendering.position(finding.span))
        facts.add_row("Observed", str(failure.value))
        facts.add_row("Allowed", failure.allowed or "nothing stated")
        return facts

    @staticmethod
    def _facts(failure: RuleFailure, finding: Finding) -> Table:
        """Return every structured fact row for one finding."""
        facts = DiagnosticRenderer._base_facts(failure, finding)
        DiagnosticRenderer._add_measurements(facts, finding)
        DiagnosticRenderer._add_evidence(facts, finding)
        DiagnosticRenderer._add_provenance(facts, finding)
        DiagnosticRenderer._add_repair(facts, finding)
        return facts

    @staticmethod
    def _model(provenance: ModelProvenance) -> str:
        """Return one compact model identity."""
        return (
            f"{provenance.backend} {provenance.model} with {provenance.reasoning_effort} reasoning"
        )

    @staticmethod
    def _syntax(finding: Finding, quoted: str) -> Syntax:
        """Return syntax-highlighted source with the finding line selected."""
        return Syntax(
            quoted,
            Syntax.guess_lexer(finding.span.path, quoted),
            line_numbers=True,
            start_line=finding.span.start_line,
            highlight_lines={finding.span.start_line},
            word_wrap=True,
        )

    @staticmethod
    def _title(failure: RuleFailure, finding: Finding) -> str:
        """Return the rule and optional fixability marker."""
        marker = CheckRendering.fixable(finding).strip()
        return f"{failure.rule} {marker}".rstrip()

    @staticmethod
    def _tokens(provenance: ModelProvenance) -> str:
        """Return compact token usage for one contextual call."""
        return (
            f"{provenance.input_tokens} input, {provenance.output_tokens} output, "
            f"{provenance.reasoning_tokens} reasoning"
        )

    def _content(self, finding: Finding, facts: Table) -> Group:
        """Combine message, facts, and available source."""
        message = Text(finding.message)
        quoted = self.source.line(finding.span.path, finding.span.start_line)
        if not quoted:
            return Group(message, facts)
        return Group(message, facts, self._syntax(finding, quoted))
