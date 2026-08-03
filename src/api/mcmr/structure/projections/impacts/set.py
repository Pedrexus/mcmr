from patos import FrozenModel

from .reached import ReachedModule


class ImpactSet(FrozenModel):
    """Hold changed modules, unresolved paths, and their import blast radius."""

    changed: list[str] = []
    unresolved: list[str] = []
    reached: list[ReachedModule] = []
