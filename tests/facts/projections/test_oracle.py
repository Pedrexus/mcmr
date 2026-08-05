from pathlib import Path

import pytest

from mcmr.commands.projection import imports
from mcmr.structure.projections import Dependency, ModuleGraph

from ...support import kernel_binary, needs_kernel
from .support import (
    archy_graphs,
    package_import_dependencies,
    reexported_surface_dependencies,
    transitive_dependencies,
    type_only_dependencies,
)


@pytest.fixture(scope="session")
def snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the source fixture read by the frozen Archy comparison."""
    copied = tmp_path_factory.mktemp("oracle") / "src"
    sources = {
        "mcmr/__init__.py": "from .queries import Query\n",
        "mcmr/api.py": """from typing import TYPE_CHECKING
from mcmr import Query
from mcmr.models import Rule
from mcmr.schema import Entry
from mcmr.engine import Runner
if TYPE_CHECKING:
    from mcmr.backend import Backend
""",
        "mcmr/backend.py": "class Backend:\n    pass\n",
        "mcmr/engine/__init__.py": "from .runtime import Runner\n",
        "mcmr/engine/runtime.py": "class Runner:\n    pass\n",
        "mcmr/models.py": "class Rule:\n    pass\n",
        "mcmr/queries.py": "class Query:\n    pass\n",
        "mcmr/schema.pyi": "class Entry:\n    pass\n",
    }
    for relative, source in sources.items():
        path = copied / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return copied


@needs_kernel
def test_the_matrix_agrees_with_the_archy_oracle_on_this_repository(snapshot: Path) -> None:
    """The frozen Archy graph classifies every intentional projection difference.

    Runtime modules and dependencies have to be the same set on the source fixture. Archy
    ignores PEP 561
    stub modules and collapses an import of one onto its package. It also omits some runtime
    imports whose target is an `__init__.py`. MCMR leaves a `TYPE_CHECKING` import out of the graph
    because it does not exist when the program runs, while Archy counts it. Our reexports are
    followed to their declaration, while Archy retains each immediate surface hop.
    """
    ours = imports(snapshot, kernel_binary())
    their_raw, their_comparable = archy_graphs(snapshot, ours)
    runtime_modules = set(their_comparable.paths)
    our_pairs = {
        (edge.importer, edge.imported)
        for edge in ours.dependencies
        if edge.importer in runtime_modules and edge.imported in runtime_modules
    }
    comparable_their_pairs = {
        (edge.importer, edge.imported) for edge in their_comparable.dependencies
    }
    type_only = type_only_dependencies(snapshot, runtime_modules)
    package_imports = package_import_dependencies(snapshot, runtime_modules, ours.paths)

    assert (
        runtime_modules,
        our_pairs - comparable_their_pairs,
        comparable_their_pairs - our_pairs,
    ) == (
        set(their_raw.paths),
        (our_pairs - comparable_their_pairs)
        & (package_imports | transitive_dependencies(comparable_their_pairs)),
        (type_only - our_pairs)
        | reexported_surface_dependencies(comparable_their_pairs, resolved=our_pairs),
    )
    assert type_only


@needs_kernel
def test_a_reexport_resolves_to_the_module_that_defines_the_name(snapshot: Path) -> None:
    """MCMR resolves an exported name while the frozen Archy graph retains its surface hop."""
    ours = imports(snapshot, kernel_binary())
    their_raw, _ = archy_graphs(snapshot, ours)
    our_pairs = {(edge.importer, edge.imported) for edge in ours.dependencies}
    their_pairs = {(edge.importer, edge.imported) for edge in their_raw.dependencies}

    assert ("mcmr.api", "mcmr.queries") in our_pairs
    assert ("mcmr.api", "mcmr") not in our_pairs
    assert ("mcmr.api", "mcmr") in their_pairs


@needs_kernel
def test_the_impact_set_agrees_with_the_archy_oracle_on_this_repository(snapshot: Path) -> None:
    """The same blast radius, over a change whose reach no `TYPE_CHECKING` import decides."""
    ours = imports(snapshot, kernel_binary())
    their_raw, their_comparable = archy_graphs(snapshot, ours)
    changed = [snapshot / "mcmr" / "queries.py"]
    projection = ours.impact(changed)
    raw_projection = their_raw.impact(changed)
    comparable_projection = their_comparable.impact(changed)

    assert set(projection.changed) == set(raw_projection.changed)
    assert {item.module for item in projection.reached} == {
        item.module for item in comparable_projection.reached
    }
    assert {item.module for item in raw_projection.reached} == {
        item.module for item in comparable_projection.reached
    }


@needs_kernel
def test_a_type_checking_import_is_the_whole_difference_from_the_oracle(snapshot: Path) -> None:
    """MCMR plus the imports that never run is Archy exactly, which pins the one difference.

    A module reached only through a `TYPE_CHECKING` import is not in the blast radius, because
    that import does not exist when the program runs, and Archy counts it anyway. Putting those
    edges back has to reproduce the oracle answer, or the difference is a defect rather than a
    decision. Both walks are the same traversal, which the exact agreement above already checks.
    """
    ours = imports(snapshot, kernel_binary())
    _, their_comparable = archy_graphs(snapshot, ours)
    our_pairs = {(edge.importer, edge.imported) for edge in ours.dependencies}
    missing = sorted(type_only_dependencies(snapshot, set(their_comparable.paths)) - our_pairs)
    widened = ModuleGraph(
        root=snapshot,
        paths=ours.paths,
        dependencies=list(ours.dependencies)
        + [
            Dependency(importer=importer, imported=imported, path=ours.paths[importer])
            for importer, imported in missing
        ],
    )
    changed = [snapshot / "mcmr" / "backend.py"]
    reached = {item.module for item in ours.impact(changed).reached}
    their_impacted = {item.module for item in their_comparable.impact(changed).reached}

    assert (bool(missing), reached) == (True, reached & their_impacted)
    assert {item.module for item in widened.impact(changed).reached} == their_impacted
