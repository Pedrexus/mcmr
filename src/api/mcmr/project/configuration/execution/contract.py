from patos import FrozenModel
from pydantic import StrictBool

from ....domain.contracts import RuleLane


class ExecutionConfiguration(FrozenModel):
    """Choose which independent classes of work one check may perform."""

    deterministic: StrictBool = True
    contextual: StrictBool = False
    external: StrictBool = False

    def includes(self, *, external: bool, lane: RuleLane) -> bool:
        """Return whether this execution contract admits one catalog definition."""
        local = not external or self.external
        enabled = self.deterministic if lane is RuleLane.DETERMINISTIC else self.contextual
        return local and enabled
