from patos import FrozenModel

from .....domain.primitives import NonEmptyStr
from .approval import ChangeApproval


class ChangeRecordFields(FrozenModel):
    """Retain change identity, review policy, and approval evidence."""

    identifier: NonEmptyStr
    author: NonEmptyStr
    review_required: bool = True
    approvals: list[ChangeApproval] = []
    emergency: bool = False
    retrospective_review: str = ""
    mechanical: bool = False
