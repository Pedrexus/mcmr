from patos import FrozenModel
from pydantic import NonNegativeInt

from ....foundation import NodeRef


class ProtectedRegion(FrozenModel):
    """Retain the protected statement and setup leading into one try region."""

    statement: NodeRef | None = None
    leading_assignments: list[NodeRef] = []
    protected_statements: list[NodeRef] = []
    leading_literal_assignment_count: NonNegativeInt = 0
    has_following_raising_operation: bool = False
