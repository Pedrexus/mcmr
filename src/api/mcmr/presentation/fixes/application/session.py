from contextlib import ExitStack
from typing import TYPE_CHECKING

from ....domain.contracts import FixSafety
from ....domain.errors import UnrenderableFix
from ...reports.data.report import CheckReport
from ..contracts import (
    FixRefusal,
    FixSignature,
    RenderedFix,
)
from ..rendering.python import PythonFixRenderer
from .result import FixResult
from .writer import AtomicFixWriter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from ....checking.session import Judgment


class FixSession:
    """Apply eligible plans and retain only fixes their own rule verifies."""

    def __init__(
        self,
        root: Path,
        judgment: Judgment,
        *,
        safety: FixSafety = FixSafety.SAFE,
        maximum_fixes: int = 100,
    ) -> None:
        self.root = root
        self.judgment = judgment
        self.safety = safety
        self.maximum_fixes = maximum_fixes
        self.renderer = PythonFixRenderer(root)
        self.writer = AtomicFixWriter(root)

    @staticmethod
    def matching(report: CheckReport, candidate: RenderedFix) -> int:
        """Count the originating rule findings whose exact message remains."""
        return sum(
            finding.message == candidate.message
            for failure in report.failures
            if failure.rule == candidate.rule
            for finding in failure.reported
        )

    def retain(
        self,
        current: CheckReport,
        candidates: list[RenderedFix],
    ) -> tuple[CheckReport, list[RenderedFix], list[FixRefusal]]:
        """Retain one compatible batch, falling back to its first plan when needed."""
        try:
            verified = self._verified(current, candidates)
        except UnrenderableFix:
            candidates, verified = self._first_verified(current, candidates)
        if verified is not None:
            return verified, candidates, []
        if len(candidates) > 1:
            return self.retain(current, candidates[: max(1, len(candidates) // 2)])
        candidate = candidates[0]
        return (
            current,
            [],
            [
                FixRefusal(
                    rule=candidate.rule,
                    summary=candidate.summary,
                    reason="the edited source parsed but the originating finding remained",
                )
            ],
        )

    def run(self, initial: CheckReport) -> FixResult:
        """Reach a bounded fixpoint, verifying compatible edits in one analysis batch."""
        current = initial
        applied: list[RenderedFix] = []
        refused: list[FixRefusal] = []
        blocked: list[FixSignature] = []
        attempted = 0
        while attempted < self.maximum_fixes:
            offered, render_refusals = self.renderer.available(current, self.safety)
            refused.extend(item for item in render_refusals if item not in refused)
            candidates = [item for item in offered if item.signature not in blocked][
                : self.maximum_fixes - attempted
            ]
            if not candidates:
                break
            current, retained, rejected = self.retain(current, candidates)
            applied.extend(retained)
            refused.extend(rejected)
            if rejected:
                blocked.append(candidates[0].signature)
            attempted += len(retained) + len(rejected)
        return FixResult(report=current, applied=applied, refused=refused)

    @classmethod
    def _improved(
        cls,
        *,
        current: CheckReport,
        verified: CheckReport,
        candidates: Sequence[RenderedFix],
    ) -> bool:
        """Require no new parse failure and less originating evidence for every plan."""
        return verified.parse_failure_count <= current.parse_failure_count and all(
            cls.matching(verified, candidate) < cls.matching(current, candidate)
            for candidate in candidates
        )

    def _first_verified(
        self,
        current: CheckReport,
        candidates: Sequence[RenderedFix],
    ) -> tuple[list[RenderedFix], CheckReport | None]:
        """Retry one conflicting batch with only its first candidate."""
        first = list(candidates[:1])
        return first, self._verified(current, first)

    def _verified(
        self,
        current: CheckReport,
        candidates: Sequence[RenderedFix],
    ) -> CheckReport | None:
        """Apply one batch atomically and restore it unless every plan closes evidence."""
        files = self.renderer.merge(candidates)
        directories = self.renderer.merge_directories(candidates)
        self.writer.apply_changes(files, directories=directories)
        with ExitStack() as rollback:
            rollback.callback(self.writer.restore_changes, files, directories=directories)
            verified = CheckReport.of(
                self.root,
                self.judgment.model_copy(update={"failure_limit": None}).run(),
            )
            if not self._improved(current=current, verified=verified, candidates=candidates):
                return None
            rollback.pop_all()
            return verified
