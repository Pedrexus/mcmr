from patos import FrozenModel

from .....domain.primitives import NonEmptyStr


class ChangeApproval(FrozenModel):
    """Retain one approval without collapsing all approvals into a verdict."""

    reviewer: NonEmptyStr
    approved: bool = True
    eligible: bool = True
