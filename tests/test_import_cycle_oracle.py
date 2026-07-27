import ast
import importlib.util
import shutil
from typing import TYPE_CHECKING

import pytest

from mcmr.facts import DependencyComponentFact
from mcmr.projections import ModuleGraph
from mcmr.repository import GraphReader
from mcmr.rules.general.deterministic.architecture.r0011 import import_cycles
from tests.oracle import BINARY, ROOT, FindingReader, Oracle, extracted, needs, needs_kernel

if TYPE_CHECKING:
    from pathlib import Path

    from mcmr.models import Reported

INSTALLED = importlib.util.find_spec("anyio")

pytestmark = [
    needs_kernel,
    needs("pylint"),
    pytest.mark.skipif(INSTALLED is None, reason="the cycle oracle needs an installed anyio"),
]

# Why a third-party checkout rather than a written fixture. A fixture stating a cycle proves only
# that the reader sees the cycle somebody wrote for it, and this rule answered zero on every real
# repository for as long as it existed while passing exactly that kind of test. anyio is real code
# nobody wrote to satisfy this suite, it holds import cycles a maintained project has lived with,
# and it is a declared dependency, so the corpus is present wherever the suite runs. It is copied
# under its own package name so one module is spelled `anyio.abc` for all three readers at once.
PACKAGE = "anyio"

# A cycle is a property of a set of modules rather than of a line, so this one comparison is over
# the names each reader puts in a cycle instead of over located findings. Everything the harness
# does own is still used here: the tool is run and its output parsed once, in one adapter.
CYCLE = Oracle.of("pylint", "R0401")


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the installed package into a root of its own, without its compiled caches."""
    root = tmp_path_factory.mktemp("cycles")
    assert INSTALLED is not None and INSTALLED.submodule_search_locations is not None
    installed = next(iter(INSTALLED.submodule_search_locations))
    shutil.copytree(installed, root / PACKAGE, ignore=shutil.ignore_patterns("*.pyc"))
    for cache in (root / PACKAGE).rglob("__pycache__"):
        shutil.rmtree(cache)
    return root


@pytest.fixture(scope="module")
def answer(checkout: Path) -> Reported[int]:
    """Return what the rule answers over the checkout, through the real kernel."""
    return judged(checkout)


@pytest.fixture(scope="module")
def components(checkout: Path) -> list[frozenset[str]]:
    """Return the cyclic components of the edges the kernel resolved, computed independently."""
    return cyclic(edges_of(checkout))


def judged(root: Path) -> Reported[int]:
    """Build the dependency family over one root and hand it to the rule."""
    return import_cycles(fact_of(root))


def fact_of(root: Path) -> DependencyComponentFact:
    """Return the one dependency fact the kernel builds for a repository."""
    facts = extracted(root, DependencyComponentFact, (".py",))
    assert len(facts) == 1, "this family answers once for the whole repository"
    found = facts[0]
    assert isinstance(found, DependencyComponentFact)
    return found


def edges_of(root: Path) -> set[tuple[str, str]]:
    """Return the module pairs the kernel resolved an import between."""
    return {(edge.source, edge.target) for edge in fact_of(root).import_edges}


def cyclic(edges: set[tuple[str, str]]) -> list[frozenset[str]]:
    """Return the groups a path runs around, computed by closure rather than by Tarjan.

    This shares no code with the rule, so a component only both halves of MCMR believe in fails
    here. Reachability is closed by repeated union until nothing grows, and two modules are in one
    cycle exactly when each reaches the other.
    """
    reaches = reachable(edges)
    looping = {source for source, target in edges if source == target}
    groups = {
        frozenset(other for other in reaches if other in reaches[name] and name in reaches[other])
        for name in reaches
    }
    return sorted((group for group in groups if len(group) > 1 or group <= looping), key=sorted)


def reachable(edges: set[tuple[str, str]]) -> dict[str, set[str]]:
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


def pylint_cycles(root: Path) -> tuple[tuple[str, ...], ...]:
    """Return every chain Pylint reports as `R0401` over one root, as the modules it names."""
    return tuple(
        tuple(found.detail.removeprefix("Cyclic import (").removesuffix(")").split(" -> "))
        for found in CYCLE.diagnostics(root)
    )


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
    return {
        (name, target)
        for name, path in owned.items()
        for node in ast.walk(ast.parse(path.read_text(), str(path)))
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
    checkout: Path, answer: Reported[int], components: list[frozenset[str]]
) -> None:
    """The whole defect was answering zero on every repository that had a cycle to report.

    Pylint enumerates the chains and this rule counts the components those chains run inside, so
    the two totals answer different questions and only their silence is comparable. What is
    compared instead is the modules, and every module this rule puts in a cycle has to be one
    Pylint names in one as well.
    """
    upstream = pylint_cycles(checkout / PACKAGE)

    assert upstream, "the checkout is an oracle only while Pylint still reports a cycle in it"
    assert answer.value >= 1, "Pylint reports a cycle here and this rule used to report none"
    assert {module for group in components for module in group} <= {
        module for cycle in upstream for module in cycle
    }


def test_the_count_agrees_with_an_independent_walk_over_the_same_edges(
    answer: Reported[int], components: list[frozenset[str]]
) -> None:
    """The rule's arithmetic is checked against a closure rather than against a second Tarjan."""
    assert answer.value == len(components)


def test_each_finding_names_every_module_of_the_component_it_counts(
    checkout: Path, answer: Reported[int], components: list[frozenset[str]]
) -> None:
    """A count says how many tangles there are and the finding has to say which modules are in one.

    Pairing a finding to a component by the arrow it points at is what makes this fail when a
    message names the members of a different component than the one it located itself in. Where
    each finding sits is read through the harness, so a message located outside the tree it was
    read from fails as well.
    """
    located = FindingReader(
        rule_id="ALL-ARCH0011", family=DependencyComponentFact, suffixes=(".py",)
    ).report(checkout)

    assert len(answer.findings) == len(components)
    assert len(located.sites) == len(components)
    assert all(site.path.endswith(".py") for site in located.sites)
    for finding in answer.findings:
        held = next(
            group for group in components if any(f"`{name}`" in finding.message for name in group)
        )
        assert all(f"`{name}`" in finding.message for name in held)


def test_a_component_sits_inside_one_the_source_itself_states(checkout: Path) -> None:
    """A component split in half would still be mutually reachable, so bound it from above too.

    The independent reading follows an import to the package a name is written against where the
    kernel follows the re-export to the module defining that name, and it keeps what a
    type-checking block states, so it holds more edges. More edges merge components and never split
    one, which makes containment the exact relation between the two answers.
    """
    stated = cyclic(source_edges(checkout))

    assert all(any(group <= wider for wider in stated) for group in cyclic(edges_of(checkout)))


def test_a_repository_stating_no_cycle_is_answered_as_stating_none() -> None:
    """MCMR's own source is the quiet case, and all three readers have to agree it is quiet."""
    assert judged(ROOT / "src").value == 0
    assert pylint_cycles(ROOT / "src" / "mcmr") == ()
    assert cyclic(source_edges(ROOT / "src")) == []


def test_the_rule_and_the_matrix_never_disagree_about_what_is_cyclic(
    checkout: Path, components: list[frozenset[str]]
) -> None:
    """Two readers of one graph disagreeing is what made the defect invisible for so long.

    `mcmr matrix` condensed the real components the whole time this rule answered zero, so the tool
    contradicted itself in two commands and nothing failed. They read the same index now and this
    is what holds them to it.
    """
    projection = ModuleGraph.of(
        GraphReader(binary=BINARY, root=checkout).read(), checkout
    ).matrix()

    assert {frozenset(cycle.members) for cycle in projection.cycles} == set(components)
