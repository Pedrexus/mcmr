from typing import Annotated, ClassVar

from annotated_types import Predicate
from patos import FrozenModel

from .evidence import Evidence
from .span import SourceSpan


class Fact(FrozenModel):
    """Identify one independently invalidated unit supplied to rules."""

    external_evidence: ClassVar[bool] = False
    key: str
    span: SourceSpan
    language: str | None = None
    evidence: Annotated[
        list[Evidence],
        Predicate(lambda claims: len(claims) == len({claim.signal for claim in claims})),
    ] = []
