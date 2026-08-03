import ast
import importlib.util
import shutil
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.facts import DependencyComponentFact
from mcmr.query import RuleQuery
from mcmr.repository import GraphReader
from mcmr.rules.general import import_cycles
from mcmr.structure.projections import ModuleGraph

from ..oracle import (
    FindingReader,
    Oracle,
    extracted,
    needs,
    needs_kernel,
    retained_fact,
    scalar,
)
from ..support import kernel_binary

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

_INSTALLED = importlib.util.find_spec("anyio")

pytestmark = [
    needs_kernel,
    needs("pylint"),
    pytest.mark.skipif(_INSTALLED is None, reason="the cycle oracle needs an installed anyio"),
]

# A written cycle proves only that a reader sees its fixture. This rule once passed that test while
# answering zero on real repositories.

# anyio is maintained code nobody wrote for this suite and is already a dependency. Copying it
# under its package name gives all three readers the same `anyio.abc` spelling.
_PACKAGE = "anyio"

# A cycle belongs to a set of modules rather than one line, so compare the module names each reader
# reports. The harness still runs and parses each tool once through its adapter.
_CYCLE = Oracle.of("pylint", "R0401")


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the installed package into a root of its own, without its compiled caches."""
    root = tmp_path_factory.mktemp("cycles")
    assert _INSTALLED is not None and _INSTALLED.submodule_search_locations is not None
    installed = next(iter(_INSTALLED.submodule_search_locations))
    shutil.copytree(installed, root / _PACKAGE, ignore=shutil.ignore_patterns("*.pyc"))
    for cache in (root / _PACKAGE).rglob("__pycache__"):
        shutil.rmtree(cache)
    return root


@pytest.fixture(scope="module")
def answer(checkout: Path) -> RuleQuery[int]:
    """Return what the rule answers over the checkout, through the real kernel."""
    return judged(checkout)


@pytest.fixture(scope="module")
def components(checkout: Path) -> list[set[str]]:
    """Return the cyclic components of the edges the kernel resolved, computed independently."""
    return cyclic(edges_of(checkout))


def judged(root: Path) -> RuleQuery[int]:
    """Build the dependency family and query its retained native table."""
    result = import_cycles.invoke_table(retained_fact(fact_of(root)), settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("the import cycle rule returned a model query")
    return cast("RuleQuery[int]", result)


def fact_of(root: Path) -> DependencyComponentFact:
    """Return the one dependency fact the kernel builds for a repository."""
    facts = extracted(root, DependencyComponentFact, ".py")
    assert len(facts) == 1, "this family answers once for the whole repository"
    found = facts[0]
    assert isinstance(found, DependencyComponentFact)
    return found


def edges_of(root: Path) -> set[tuple[str, str]]:
    """Return the module pairs the kernel resolved an import between."""
    return {(edge.source, edge.target) for edge in fact_of(root).import_edges}


def cyclic(edges: set[tuple[str, str]]) -> list[set[str]]:
    """Return the groups a path runs around, computed by closure rather than by Tarjan.

    This shares no code with the rule, so a component only both halves of MCMR believe in fails
    here. Reachability is closed by repeated union until nothing grows, and two modules are in one
    cycle exactly when each reaches the other.
    """
    reaches = reachable(edges)
    looping = {source for source, target in edges if source == target}
    groups: list[set[str]] = []
    for name in reaches:
        group = {other for other in reaches if other in reaches[name] and name in reaches[other]}
        if group not in groups:
            groups.append(group)
    return sorted((group for group in groups if len(group) > 1 or group <= looping), key=sorted)


def reachable(edges: Collection[tuple[str, str]]) -> dict[str, set[str]]:
    """Return every node each node reaches through the edges, itself included."""
    reaches: dict[str, set[str]] = {name: {name} for pair in edges for name in pair}
    for source, target in edges:
        reaches[source].add(target)
    growing = True
    while growing:
        growing = False
        for name, reached in reaches.items():
            grown = reached.union(*(reaches[step] for step in reached))
            growing = growing or grown != reached
            reaches[name] = grown
    return reaches


def pylint_cycles(root: Path) -> list[list[str]]:
    """Return every chain Pylint reports as `R0401` over one root, as the modules it names."""
    return [
        found.detail.removeprefix("Cyclic import (").removesuffix(")").split(" -> ")
        for found in _CYCLE.diagnostics(root)
    ]


def source_edges(root: Path) -> set[tuple[str, str]]:
    """Return the import edges an independent reading of the source states.

    This is the third oracle and it shares nothing with the kernel. It names a module by its path,
    resolves a relative import against the package that wrote it, and keeps every module a `from`
    line could be naming, so it reads more edges than the kernel does rather than fewer.
    """
    owned = {}
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        owned[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = path
    imports = (
        (name, path, node)
        for name, path in owned.items()
        for node in ast.walk(ast.parse(path.read_text(), str(path)))
    )
    return {
        (name, target)
        for name, path, node in imports
        for target in named(node, name if path.name == "__init__.py" else name.rpartition(".")[0])
        if target in owned and target != name
    }


def named(node: ast.AST, package: str) -> list[str]:
    """Return every module one import statement could be naming, from the package that wrote it."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    base = package
    for _ in range(max(node.level - 1, 0)):
        base = base.rpartition(".")[0]
    stem = f"{base}.{node.module}" if node.level and node.module else (node.module or base)
    return [stem, *(f"{stem}.{alias.name}" for alias in node.names)]


def test_a_real_checkout_pylint_calls_cyclic_is_one_this_rule_calls_cyclic_too(
    checkout: Path, answer: RuleQuery[int], components: Sequence[set[str]]
) -> None:
    """The whole defect was answering zero on every repository that had a cycle to report.

    Pylint enumerates the chains and this rule counts the components those chains run inside, so
    the two totals answer different questions and only their silence is comparable. What is
    compared instead is the modules, and every module this rule puts in a cycle has to be one
    Pylint names in one as well.
    """
    upstream = pylint_cycles(checkout / _PACKAGE)

    assert upstream, "the checkout is an oracle only while Pylint still reports a cycle in it"
    value = scalar(answer)
    assert isinstance(value, int)
    assert value >= 1, "Pylint reports a cycle here and this rule used to report none"
    assert {module for group in components for module in group} <= {
        module for cycle in upstream for module in cycle
    }


def test_the_count_agrees_with_an_independent_walk_over_the_same_edges(
    answer: RuleQuery[int], components: Sequence[set[str]]
) -> None:
    """The rule's arithmetic is checked against a closure rather than against a second Tarjan."""
    assert scalar(answer) == len(components)


def test_each_finding_names_every_module_of_the_component_it_counts(
    checkout: Path, answer: RuleQuery[int], components: Sequence[set[str]]
) -> None:
    """A count says how many tangles there are and the finding has to say which modules are in one.

    Pairing a finding to a component by the arrow it points at is what makes this fail when a
    message names the members of a different component than the one it located itself in. Where
    each finding sits is read through the harness, so a message located outside the tree it was
    read from fails as well.
    """
    located = FindingReader(
        rule_id="ALL-ARCH0002", family=DependencyComponentFact, suffixes=(".py",)
    ).report(checkout)

    assert answer.findings is not None
    findings = list(answer.findings.rows.collect().iter_rows(named=True))
    assert len(findings) == len(components)
    assert len(located.sites) == len(components)
    assert all(site.path.endswith(".py") for site in located.sites)
    for finding in findings:
        held = next(
            group
            for group in components
            if any(f"`{name}`" in finding["message"] for name in group)
        )
        assert all(f"`{name}`" in finding["message"] for name in held)


def test_a_component_sits_inside_one_the_source_itself_states(checkout: Path) -> None:
    """A component split in half would still be mutually reachable, so bound it from above too.

    The independent reading follows an import to the package a name is written against where the
    kernel follows the re-export to the module defining that name, and it keeps what a
    type-checking block states, so it holds more edges. More edges merge components and never split
    one, which makes containment the exact relation between the two answers.
    """
    stated = cyclic(source_edges(checkout))

    assert all(any(group <= wider for wider in stated) for group in cyclic(edges_of(checkout)))


def test_a_repository_stating_no_cycle_is_answered_as_stating_none(tmp_path: Path) -> None:
    """An acyclic repository is the quiet case, and all three readers have to agree."""
    package = tmp_path / "quiet"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from .service import run\n",
        encoding="utf-8",
    )
    (package / "service.py").write_text(
        "def run():\n    return 1\n",
        encoding="utf-8",
    )

    assert scalar(judged(tmp_path)) == 0
    assert pylint_cycles(package) == []
    assert cyclic(source_edges(tmp_path)) == []


def test_the_rule_and_the_matrix_never_disagree_about_what_is_cyclic(
    checkout: Path, components: Sequence[set[str]]
) -> None:
    """Two readers of one graph disagreeing is what made the defect invisible for so long.

    `mcmr matrix` condensed the real components the whole time this rule answered zero, so the tool
    contradicted itself in two commands and nothing failed. They read the same index now and this
    is what holds them to it.
    """
    projection = ModuleGraph.of(
        GraphReader(binary=kernel_binary(), root=checkout).read(), checkout
    ).matrix()

    matrix_cycles = [set(cycle.members) for cycle in projection.cycles]
    assert len(matrix_cycles) == len(components)
    assert all(cycle in components for cycle in matrix_cycles)
