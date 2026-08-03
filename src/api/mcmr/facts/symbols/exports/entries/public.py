from patos import FrozenModel
from pydantic import NonNegativeInt

from .....domain.primitives import NonEmptyStr
from ....foundation import NodeRef, SourceSpan


class PublicExport(FrozenModel):
    """Retain one explicit export and use of that public route."""

    name: NonEmptyStr
    target: NonEmptyStr
    consumer_count: NonNegativeInt = 0
    nodes: list[NodeRef] = []
    span: SourceSpan
