from patos import FrozenModel

from ....checking.evaluations import PreparedRule
from ....domain.policy import Policy
from ...contracts import RuleQuery


class ResolvedRule(FrozenModel):
    """Carry one prepared rule and every value resolved for its execution."""

    prepared: PreparedRule
    policy: Policy | None
    fix_count: int
    query: RuleQuery
    accepted_paths: list[str]
