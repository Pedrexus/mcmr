from patos import FrozenModel

from .....facts import SourceSpan
from ....primitives import RuleValue
from ...repair import Finding


class Observation(FrozenModel):
    """Retain one rule value beside the fact and evidence behind it."""

    rule: str
    fact: str
    value: RuleValue
    span: SourceSpan = SourceSpan(path="")
    findings: list[Finding] = []
