from typing import TYPE_CHECKING

from patos import FrozenModel

from .contracts import Verdict
from .decisions import Boolean, Category, Numeric

if TYPE_CHECKING:
    from ..contracts import RuleValue
    from .contracts import Policy

type RulePolicy = Numeric | Boolean | Category


def allowed(policy: Policy | None) -> str:
    """Render what one rule's effective policy accepts."""
    if isinstance(policy, Boolean):
        return str(policy.expected)
    if isinstance(policy, Category):
        groups = {"good": policy.good, "neutral": policy.neutral, "bad": policy.bad}
        return " | ".join(
            f"{name} {', '.join(sorted(values))}" for name, values in groups.items() if values
        )
    if not isinstance(policy, Numeric):
        return ""
    if policy.minimum is None:
        return f"<= {policy.maximum:g}"
    return (
        f">= {policy.minimum:g}"
        if policy.maximum is None
        else f"{policy.minimum:g}..{policy.maximum:g}"
    )


class RulePolicies(FrozenModel):
    """Apply rule-owned acceptance contracts and exact project overrides."""

    overrides: dict[str, RulePolicy] = {}

    def decide(
        self,
        value: RuleValue,
        *,
        rule_id: str,
        candidate: RulePolicy | None,
    ) -> Verdict:
        """Return the verdict for one observation under its effective rule policy."""
        policy = self.policy(rule_id=rule_id, candidate=candidate)
        return policy.verdict(value) if policy else Verdict.UNASSESSED

    def policy(
        self,
        *,
        rule_id: str,
        candidate: RulePolicy | None,
    ) -> Policy | None:
        """Return one project override or the rule-owned acceptance contract."""
        return self.overrides.get(rule_id, candidate)
