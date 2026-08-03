from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .edge import DependencyEdge


class DependencyComponentFact(Fact):
    """Describe the import graph of one repository."""

    import_edges: list[DependencyEdge] = []
