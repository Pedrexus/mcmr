from patos import FrozenModel

from ....primitives.scope import RuleScope
from ...runtime import RuleId, RuleLane


class RuleIdentity(FrozenModel):
    """Identify one rule and the fact family where it belongs."""

    id: RuleId
    callable: str
    scope: RuleScope
    lane: RuleLane
    external: bool = False
    family: str
    fact: str
