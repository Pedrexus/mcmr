from typing import TYPE_CHECKING

from .protected import ProtectedRegion

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from .handler import ExceptionHandler


class ExceptionRegion(ProtectedRegion):
    """Retain protected setup and executable clause sizes for one try statement."""

    clause_statement_counts: list[NonNegativeInt] = []
    handlers: list[ExceptionHandler] = []
    has_else: bool = False
    has_finally: bool = False
    is_exception_group: bool = False
