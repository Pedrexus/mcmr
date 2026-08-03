from patos import FrozenModel

from ....domain.primitives import NonEmptyStr
from ...foundation import SourceSpan


class TypingDefinition(FrozenModel):
    """Locate one reusable typing declaration."""

    name: NonEmptyStr
    span: SourceSpan
