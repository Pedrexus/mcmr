from patos import FrozenModel
from pydantic import NonNegativeInt


class ReplacementAudit(FrozenModel):
    """State exact replacement coverage and every ledger inconsistency."""

    legacy_rules: NonNegativeInt
    mapped_rules: NonNegativeInt
    legacy_capabilities: NonNegativeInt
    mapped_capabilities: NonNegativeInt
    missing_capabilities: NonNegativeInt
    issues: list[str] = []

    @property
    def complete(self) -> bool:
        """Whether every old rule and behavior has a valid final disposition."""
        return not self.issues and self.missing_capabilities == 0
