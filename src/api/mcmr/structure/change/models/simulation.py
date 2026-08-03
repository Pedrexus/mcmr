from patos import FrozenModel

from ...projections import Cycle, Dependency
from .applied import AppliedChange


class Simulation(FrozenModel):
    """Describe the graph after a proposed change without claiming a source verdict."""

    applied: AppliedChange
    cycles_formed: list[Cycle] = []
    cycles_broken: list[Cycle] = []
    back_edges_formed: list[Dependency] = []
    back_edges_cleared: list[Dependency] = []
    propagation_before: float = 0.0
    propagation_after: float = 0.0
