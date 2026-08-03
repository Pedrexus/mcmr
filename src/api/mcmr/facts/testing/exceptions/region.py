from patos import FrozenModel
from pydantic import NonNegativeInt

from ...foundation import NodeRef
from .handler import ExceptionHandler


class ExceptionRegion(FrozenModel):
    """Retain protected setup and executable clause sizes for one try statement."""

    leading_literal_assignment_count: NonNegativeInt = 0
    has_following_raising_operation: bool = False
    clause_statement_counts: list[NonNegativeInt] = []
    statement: NodeRef | None = None
    leading_assignments: list[NodeRef] = []
    protected_statements: list[NodeRef] = []
    handlers: list[ExceptionHandler] = []
    has_else: bool = False
    has_finally: bool = False
    is_exception_group: bool = False
