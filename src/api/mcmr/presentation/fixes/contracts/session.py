from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...reports import CheckReportFields


class JudgmentRunner(Protocol):
    """Run a repeatable judgment after applying a candidate fix."""

    def model_copy(self, *, update: Mapping[str, int | None]) -> Self: ...

    def run(self) -> CheckReportFields.Judgment: ...
