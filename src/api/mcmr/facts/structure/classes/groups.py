from patos import FrozenModel
from pydantic import NonNegativeInt

from ...foundation import MemberKind, SourceSpan, Visibility


class MethodAnalysisFields(FrozenModel):
    """Retain method identity, source, region, kind, visibility, and decorators."""

    name: str
    span: SourceSpan
    source: str = ""
    region: NonNegativeInt = 0
    kind: MemberKind = MemberKind.METHOD
    visibility: Visibility = Visibility.PUBLIC
    decorators: list[str] = []
