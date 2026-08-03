from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel

from ..contracts import Dependency
from ..impacts import ImpactSet, ReachedModule

if TYPE_CHECKING:
    from collections.abc import Sequence


class ImpactTraversal(FrozenModel):
    """Walk reversed imports from a set of changed repository paths."""

    root: Path
    paths: dict[str, str]
    dependencies: list[Dependency]

    def distances(self, origins: list[str]) -> dict[str, int]:
        """Return the shortest reversed-import distance from every reached module."""
        importers = self.importers()
        distance = dict.fromkeys(origins, 0)
        pending = deque(origins)
        while pending:
            module = pending.popleft()
            for importer in importers.get(module, []):
                if importer not in distance:
                    distance[importer] = distance[module] + 1
                    pending.append(importer)
        return distance

    def importers(self) -> dict[str, list[str]]:
        """Return the sorted modules that import each module."""
        found: dict[str, list[str]] = {}
        for edge in self.dependencies:
            found.setdefault(edge.imported, []).append(edge.importer)
        return {module: sorted(names) for module, names in found.items()}

    def walk(self, changed: Sequence[Path]) -> ImpactSet:
        """Return changed modules, unresolved paths, and every module that reaches them."""
        owners = {(self.root / path).resolve(): module for module, path in self.paths.items()}
        named = {path: owners.get(path.resolve()) for path in changed}
        origins = sorted({module for module in named.values() if module is not None})
        distances = self.distances(origins)
        reached = [
            ReachedModule(module=module, path=self.paths[module], distance=hops)
            for module, hops in sorted(distances.items(), key=lambda found: (found[1], found[0]))
            if hops
        ]
        return ImpactSet(
            changed=origins,
            unresolved=sorted(str(path) for path, module in named.items() if module is None),
            reached=reached,
        )
