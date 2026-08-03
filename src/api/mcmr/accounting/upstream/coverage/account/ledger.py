from functools import cached_property
from importlib.resources import files

from patos import FrozenModel

from .gap import Gap


class GapAccount(FrozenModel):
    """Hold every gap recorded beside one tool inventory and its fallback."""

    tool: str
    default: Gap
    gaps: list[Gap] = []

    @cached_property
    def by_group(self) -> dict[str, Gap]:
        """Return the gap each named group falls to, first statement winning."""
        return {group: gap for gap in reversed(self.gaps) for group in gap.groups}

    @cached_property
    def by_symbol(self) -> dict[str, Gap]:
        """Return the gap each named symbol falls to, first statement winning."""
        return {symbol: gap for gap in reversed(self.gaps) for symbol in gap.symbols}

    @classmethod
    def load(cls, tool: str) -> GapAccount:
        """Read the gap account this package records for one tool."""
        source = files("mcmr.data").joinpath(f"{tool}.gaps.json").read_text()
        return cls.model_validate_json(source)

    def gap(self, *, symbol: str, group: str) -> Gap:
        """Return what happens to one rule, from its symbol and then its group."""
        stated = self.by_symbol.get(symbol) or self.by_group.get(group)
        return stated or self.default
