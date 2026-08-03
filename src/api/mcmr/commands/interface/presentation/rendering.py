from collections import Counter
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.syntax import Syntax

from ....domain.contracts import FixSafety
from ..surface import readable_table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import Console

    from ....presentation.fixes import FixRefusal, RenderedFix


class FixPresentation:
    """Present applied, previewed, and refused fixes with their safety."""

    def __init__(self, terminal: Console) -> None:
        self.terminal = terminal

    def show(
        self,
        *,
        applied: Sequence[RenderedFix],
        previewed: Sequence[RenderedFix],
        refused: Sequence[FixRefusal],
    ) -> None:
        """Print the fix ledger followed by every patch that still needs review."""
        if not applied and not previewed and not refused:
            return
        table = readable_table("Autofix")
        for heading in ("State", "Rule", "Safety", "Plan", "Detail"):
            table.add_column(heading)
        table.add_column("Count", justify="right")
        rows = self._rows(applied=applied, previewed=previewed, refused=refused)
        for row, count in rows.items():
            table.add_row(*row, str(count))
        self.terminal.print(table)
        for fix in previewed:
            self._preview(fix)

    @staticmethod
    def _rows(
        *,
        applied: Sequence[RenderedFix],
        previewed: Sequence[RenderedFix],
        refused: Sequence[FixRefusal],
    ) -> Counter[tuple[str, str, str, str, str]]:
        """Count matching ledger rows before presentation."""
        return Counter(
            [("applied", fix.rule, fix.safety, fix.summary, "rule verified") for fix in applied]
            + [("preview", fix.rule, fix.safety, fix.summary, "diff only") for fix in previewed]
            + [("refused", item.rule, "", item.summary, item.reason) for item in refused]
        )

    def _preview(self, fix: RenderedFix) -> None:
        """Render one reviewable diff with safety-aware emphasis."""
        self.terminal.print(
            Panel(
                Syntax(fix.diff, "diff", background_color="default", word_wrap=True),
                title=f"{fix.rule}  {fix.safety} preview",
                title_align="left",
                border_style="green" if fix.safety is FixSafety.SAFE else "yellow",
            )
        )
