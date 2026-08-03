from typing import TYPE_CHECKING

from .groups import MethodAnalysisFields

if TYPE_CHECKING:
    from collections.abc import Sequence


class MethodAnalysis(MethodAnalysisFields):
    """Retain ordering and binding facts for one declared method."""

    is_protocol_name: bool = False
    reads_receiver: bool = False
    reads_receiver_state: bool = False
    owner_qualified_calls: list[str] = []

    def order_key(
        self,
        *,
        lifecycle: Sequence[str],
        visibility_order: Sequence[str],
        kind_order: Sequence[str],
        alphabetical: bool,
    ) -> tuple[int, int, int, str]:
        """Return this method's position under one declared member order."""
        if self.name in lifecycle:
            return (0, lifecycle.index(self.name), 0, "")
        if self.is_protocol_name:
            return (1, 0, 0, self.name.casefold() if alphabetical else "")
        return (
            2,
            self._rank(visibility_order, self.visibility),
            self._rank(kind_order, self.kind),
            self.name.casefold() if alphabetical else "",
        )

    @staticmethod
    def _rank(order: Sequence[str], value: str) -> int:
        """Return a value's declared position or the trailing position."""
        return order.index(value) if value in order else len(order)
