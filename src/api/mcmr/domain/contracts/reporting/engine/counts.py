from typing import TYPE_CHECKING

from .groups import EngineCountFields

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class EngineCounts(EngineCountFields.Execution):
    """Count the catalog and query work represented by one engine report."""

    @property
    def skipped_rule_count(self) -> NonNegativeInt:
        """Count skipped rules from their authoritative identities."""
        return len(self.skipped_rules)
