from patos import FrozenModel

from ...foundation import SourceSpan


class ParameterUseFields(FrozenModel):
    """Retain parameter name, owner, source span, and annotation."""

    name: str = ""
    owner: str = ""
    span: SourceSpan | None = None
    annotation: str
