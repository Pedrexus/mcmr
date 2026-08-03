from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import InstanceOf

from ....inventory.contracts import Inventory, ToolRule
from ...profiles.coverage import Coverage
from ...profiles.tools import ToolProfile, ToolRegistry
from ...references import ClaimIndex
from ..account import CoverageEntry, GapAccount

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...references import Reference


class ToolCoverage(FrozenModel):
    """Account for every rule one upstream tool ships, one entry each."""

    tool: str
    claims: InstanceOf[ClaimIndex]

    @cached_property
    def account(self) -> GapAccount:
        """Return the gaps recorded beside this tool's inventory."""
        return GapAccount.load(self.profile.slug)

    @cached_property
    def entries(self) -> list[CoverageEntry]:
        """Return one entry for every rule the inventory holds."""
        return [self.entry(rule) for rule in self.inventory.rules]

    @cached_property
    def inventory(self) -> Inventory:
        """Return the frozen inventory of the tool this report accounts for."""
        return Inventory.load(self.profile.slug)

    @cached_property
    def profile(self) -> ToolProfile:
        """Return the registered profile of the tool this report accounts for."""
        profile = ToolRegistry().of(self.tool)
        if profile is None:
            raise ValueError(f"{self.tool} is not a registered upstream tool")
        return profile

    def claims_for(self, rule: ToolRule) -> Sequence[Reference]:
        """Return the claims that cover this tool and one inventory rule."""
        return [
            claim
            for claim in self.claims.of(
                tool=self.profile.name,
                code=rule.code,
                symbol=rule.symbol,
            )
            if claim.covers(self.profile)
        ]

    def entry(self, rule: ToolRule) -> CoverageEntry:
        """Return what MCMR does about one rule, reading claims before gaps."""
        claimed = self.claims_for(rule)
        if not claimed:
            gap = self.account.gap(symbol=rule.symbol, group=rule.group)
            return CoverageEntry(rule=rule, coverage=gap.coverage, reason=gap.reason)
        exact = any(claim.coverage is Coverage.NATIVE for claim in claimed)
        named = ", ".join(claim.rule for claim in claimed)
        answers = " ".join(claim.summary for claim in claimed)
        return CoverageEntry(
            rule=rule,
            coverage=Coverage.NATIVE if exact else Coverage.ADAPTED,
            reason=f"MCMR {'generalizes' if exact else 'adapts'} this rule as {named}. {answers}",
            rules=[claim.rule for claim in claimed],
        )

    def tally(self) -> dict[Coverage, int]:
        """Return how many rules fall into each state."""
        return {
            coverage: sum(entry.coverage is coverage for entry in self.entries)
            for coverage in Coverage
        }
