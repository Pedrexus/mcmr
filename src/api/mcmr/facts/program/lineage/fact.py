from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .edge import LineageEdge


class LineageEdgeFact(Fact):
    """Describe one resolved data lineage edge."""

    external_evidence = True
    edges: list[LineageEdge] = []
