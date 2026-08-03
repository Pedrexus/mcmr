from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..projections import ModuleGraph


def propagation(graph: ModuleGraph) -> float:
    """Return the average share of the repository reached by one module edit."""
    importers = graph.importers()
    modules = sorted(graph.paths)
    if not modules:
        return 0.0
    total = 0
    for module in modules:
        reached = {module}
        pending = deque([module])
        while pending:
            unseen = set(importers.get(pending.popleft(), ())) - reached
            reached.update(unseen)
            pending.extend(unseen)
        total += len(reached)
    return total / len(modules) ** 2
