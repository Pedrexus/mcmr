from patos import FrozenModel

from ..contracts import Cycle, Dependency
from .cell import MatrixCell


class DesignStructureMatrix(FrozenModel):
    """Hold one ordered module dependency matrix and its cycles."""

    ordering: list[str] = []
    cells: list[MatrixCell] = []
    cycles: list[Cycle] = []
    back_edges: list[Dependency] = []
