import textwrap
from abc import ABC, abstractmethod
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import NonNegativeInt, PositiveInt

from .bases import FrozenFlexModel
from .facts import SourceSpan
from .models import Edit, Finding, FixSafety, RuleValue
from .policy import Verdict
from .runs import Verdicts, allowed

if TYPE_CHECKING:
    from .projections import Rendering
    from .runs import Assessment


class SourceReader(FrozenFlexModel):
    """Read back the exact lines a diagnostic quotes, once per file that has one.

    A report over a large repository would otherwise reread a tree the kernel has already walked,
    so a file is opened only when a finding points into it and its lines are kept for the rest of
    the run. A path nothing can read leaves the excerpt out rather than failing the report, since
    a synthesized span naming a file the tree no longer holds is still a finding worth printing.
    """

    root: Path
    opened: dict[str, list[str]] = {}

    def line(self, path: str, number: int) -> str:
        """Return one source line, or nothing at all when the file cannot answer for it."""
        if path not in self.opened:
            self.opened[path] = self.text(path)
        held = self.opened[path]
        return held[number - 1] if 0 < number <= len(held) else ""

    def text(self, path: str) -> list[str]:
        """Return every line of one file, or nothing when it cannot be read."""
        try:
            return (self.root / path).read_text().splitlines()
        except OSError:
            return []


class RuleFailure(FrozenFlexModel):
    """One rule that failed at one site, with everything a reader or an agent acts on.

    The identifier and the number are what the old table held. What was missing is the sentence
    the rule already promised in its own documentation, the place a reader opens, and the findings
    that say which thing inside that place produced the number.
    """

    rule: str
    summary: str
    where: str
    span: SourceSpan
    value: RuleValue
    allowed: str
    findings: tuple[Finding, ...] = ()

    @classmethod
    def of(cls, assessment: Assessment, bar: str) -> RuleFailure:
        """Return the failure one judged assessment states."""
        return cls(
            rule=assessment.definition.id,
            summary=assessment.definition.documentation.summary,
            where=assessment.observation.fact,
            span=assessment.observation.span,
            value=assessment.observation.value,
            allowed=bar,
            findings=assessment.observation.findings,
        )

    @property
    def reported(self) -> tuple[Finding, ...]:
        """Return what this failure has to say, which is one line even before it has findings.

        A rule that has not migrated still has to appear somewhere a reader can open, so its
        summary and the span of the fact it read stand in for the finding it does not state yet.
        The difference between the two is visible on the page rather than hidden, which is what
        keeps the migration honest.
        """
        return self.findings or (Finding(message=self.summary, span=self.span),)


class CheckReport(FrozenFlexModel):
    """What one pass of the catalog concluded about a repository, before anybody renders it.

    Every rendering reads this, so two registers of the same report can never disagree about what
    was found. Every failure is here rather than only the first few, because bounding the view is
    the reader's decision rather than the report's.
    """

    root: str
    profile: str
    file_count: NonNegativeInt = 0
    fact_count: NonNegativeInt = 0
    invocation_count: NonNegativeInt = 0
    unassessed_count: NonNegativeInt = 0
    kernel_milliseconds: float = 0.0
    rule_milliseconds: float = 0.0
    failures: tuple[RuleFailure, ...] = ()

    @classmethod
    def of(cls, root: Path, judged: Verdicts) -> CheckReport:
        """Return the report one judgment makes, with its failures in the order it found them."""
        return cls(
            root=str(root),
            profile=judged.profile.name,
            file_count=judged.kernel.file_count,
            fact_count=judged.kernel.fact_count,
            invocation_count=judged.engine.invocation_count,
            unassessed_count=judged.unassessed_count,
            kernel_milliseconds=judged.kernel.extraction_nanoseconds / 1_000_000,
            rule_milliseconds=judged.engine.execution_nanoseconds / 1_000_000,
            failures=tuple(
                RuleFailure.of(item, allowed(judged.profile.policy(item.definition)))
                for item in judged.assessments
                if item.verdict is Verdict.FAIL
            ),
        )

    @property
    def finding_count(self) -> int:
        """Return how many findings the failures of this run carry between them."""
        return sum(len(failure.findings) for failure in self.failures)


class CheckRendering(FrozenFlexModel, ABC):
    """Render one check for a terminal, in whichever register the reader asked for.

    Both registers answer a person and a program with the same bytes, which is why there is no
    structured side channel here. The concise one is a line somebody greps and a program splits on
    its first colons. The full one quotes the source and points at the span inside it.
    """

    limit: NonNegativeInt = 20

    def render(self, projection: CheckReport) -> str:
        """State every failure this view holds, then what the whole run cost."""
        shown = projection.failures[: self.limit]
        omitted = len(projection.failures) - len(shown)
        source = SourceReader(root=Path(projection.root))
        return "\n".join(
            [
                *(
                    line
                    for failure in shown
                    for finding in failure.reported
                    for line in self.diagnostic(failure, finding, source)
                ),
                *([f"and {omitted} more failures"] if omitted else []),
                "",
                f"{projection.file_count} files, {projection.fact_count} facts, "
                f"{projection.invocation_count} invocations, {len(projection.failures)} failures, "
                f"{projection.finding_count} findings, {projection.unassessed_count} unassessed, "
                f"kernel {projection.kernel_milliseconds:.0f} ms, "
                f"rules {projection.rule_milliseconds:.0f} ms",
            ]
        )

    @abstractmethod
    def diagnostic(
        self, failure: RuleFailure, finding: Finding, source: SourceReader
    ) -> list[str]:
        """Return the lines one finding of one failure takes in this register."""

    @staticmethod
    def position(span: SourceSpan) -> str:
        """Return where a finding is, in the file, line, and column an editor jumps to."""
        return f"{span.path}:{span.start_line}:{span.start_column + 1}"

    @staticmethod
    def fixable(finding: Finding) -> str:
        """Return the marker a finding carries when an edit closes it, and how far that edit goes.

        Only a repair the backend can render earns a mark, and the two marks are the two promises
        it can make. `[*]` is ruff's and means the edit is safe to apply unattended. `[?]` means an
        edit exists and wants a reader first. The import cleanup that would have deleted two live
        bindings alongside the unused one was marked `[*]` for exactly as long as this read the
        repair's kind instead of its safety. Printing nothing for the second would hide a repair
        worth having and trade an overstatement for an omission.

        A choice somebody has to make carries no mark at all and is still printed, under `help`,
        because saying what the decision is beats pretending it is automatic.
        """
        if not isinstance(finding.repair, Edit):
            return ""
        return " [*]" if finding.repair.safety is FixSafety.SAFE else " [?]"


class ConciseText(CheckRendering):
    """Render each finding as one line carrying its position, its rule, and what it says.

    Nothing here opens a file, which is the point of the register. A reader piping a whole
    repository through `grep` is not waiting for the tree to be read a second time.
    """

    def diagnostic(
        self, failure: RuleFailure, finding: Finding, source: SourceReader
    ) -> list[str]:
        """Return the single line this register prints, which quotes no source at all."""
        return [
            f"{self.position(finding.span)}: {failure.rule}{self.fixable(finding)} "
            f"{finding.message} ({failure.value}, allowed "
            f"{failure.allowed or 'nothing stated'})"
        ]


class FullText(CheckRendering):
    """Render each finding as the diagnostic block rustc and ruff taught everybody to read."""

    width: PositiveInt = 96

    def diagnostic(
        self, failure: RuleFailure, finding: Finding, source: SourceReader
    ) -> list[str]:
        """Return the header, the quoted source, and every note and repair this finding has."""
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
            f"note: the rule read {failure.value} where {failure.allowed or 'nothing'} is allowed",
            *([f"note: {measured}"] if measured else []),
            *([f"help: {finding.repair.summary}"] if finding.repair is not None else []),
            "",
        ]

    def excerpt(self, span: SourceSpan, source: SourceReader) -> list[str]:
        """Return the source a span covers, marked underneath, or nothing if it cannot be read.

        A span over several lines quotes only its first and its last, because a class two hundred
        lines long is still one finding and a reader scrolling through its body has lost the
        thread the diagnostic was holding. A span covering nothing at all names a file rather than
        a place in one, so it is left as the arrow and never dressed up with a caret under
        whatever happens to sit on the first line.
        """
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


class CheckFormat(StrEnum):
    """Say which register a check is printed in, since both answer a reader and a program."""

    FULL = auto()
    CONCISE = auto()

    def check(self, limit: int) -> Rendering[CheckReport]:
        """Return the rendering a check report takes in this register."""
        return FullText(limit=limit) if self is CheckFormat.FULL else ConciseText(limit=limit)
