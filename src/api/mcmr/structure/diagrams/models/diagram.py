from patos import FrozenModel

from .edge import DiagramEdge
from .node import DiagramNode


class Diagram(FrozenModel):
    """Hold one deterministic repository diagram independently of its notation."""

    title: str
    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
