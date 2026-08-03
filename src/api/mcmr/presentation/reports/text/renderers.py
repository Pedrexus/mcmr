import textwrap
from typing import TYPE_CHECKING

from pydantic import Field

from .base import CheckRendering

if TYPE_CHECKING:
    from ....domain.contracts import Finding
    from ....facts.foundation import SourceSpan
    from ..data.report.failure import RuleFailure
    from ..data.source import SourceReader


class _TextRenderers:
    """Own the plain diagnostic renderers selected by one check format."""

    class ConciseText(CheckRendering):
        """Render each finding as one position, rule, and message line."""

        def diagnostic(
            self,
            failure: RuleFailure,
            finding: Finding,
            source: SourceReader,
        ) -> list[str]:
            """Return the single line this register prints without reading source."""
            return [
                f"{self.position(finding.span)}: {failure.rule}{self.fixable(finding)} "
                f"{finding.message} ({failure.value}, allowed "
                f"{failure.allowed or 'nothing stated'})"
            ]

    class FullText(CheckRendering):
        """Render each finding as the diagnostic block rustc and Ruff established."""

        width: int = Field(default=96, gt=0)

        @staticmethod
        def excerpt(span: SourceSpan, source: SourceReader) -> list[str]:
            """Return the bounded source a span covers with an underline."""
            if span.end_line == span.start_line and span.end_column <= span.start_column:
                return []
            opening = source.line(span.path, span.start_line)
            if not opening:
                return []
            width = len(str(span.end_line))
            edge = " " * width
            if span.end_line == span.start_line:
                return [
                    f"{edge} |",
                    f"{span.start_line:>{width}} | {opening}",
                    f"{edge} | {' ' * span.start_column}"
                    f"{'^' * max(min(span.end_column, len(opening)) - span.start_column, 1)}",
                    f"{edge} |",
                ]
            return [
                f"{edge} |",
                f"{span.start_line:>{width}} | / {opening}",
                f"{edge} ...",
                f"{span.end_line:>{width}} | | {source.line(span.path, span.end_line)}",
                f"{edge} | |{'_' * max(span.end_column, 1)}^",
                f"{edge} |",
            ]

        def diagnostic(
            self,
            failure: RuleFailure,
            finding: Finding,
            source: SourceReader,
        ) -> list[str]:
            """Return the header, quoted source, notes, and repair."""
            measured = ", ".join(item.rendered for item in finding.measurements)
            return [
                *textwrap.wrap(
                    f"{failure.rule}{self.fixable(finding)} {finding.message}",
                    width=self.width,
                    break_long_words=False,
                    break_on_hyphens=False,
                ),
                f"  --> {self.position(finding.span)}",
                *self.excerpt(finding.span, source),
                f"note: the rule read {failure.value} where "
                f"{failure.allowed or 'nothing'} is allowed",
                *([f"note: {measured}"] if measured else []),
                *([f"help: {finding.repair.summary}"] if finding.repair is not None else []),
                "",
            ]


ConciseText = _TextRenderers.ConciseText
FullText = _TextRenderers.FullText
