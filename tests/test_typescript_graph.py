from typing import TYPE_CHECKING

import pytest

from mcmr.diagrams import DiagramBuilder, DiagramKind, MemberKind, RelationKind
from mcmr.facts import ModuleCouplingFact, OverrideFact
from mcmr.kernel import Kernel
from mcmr.projections import ModuleGraph
from mcmr.repository import (
    EdgeKind,
    GraphReader,
    Language,
    NodeKind,
    RepositoryGraph,
    Resolution,
    Visibility,
)
from mcmr.rules.general.deterministic.architecture.r0012 import (
    dependency_on_a_less_stable_module,
)
from mcmr.rules.general.deterministic.architecture.r0013 import (
    concrete_module_the_repository_leans_on,
)
from mcmr.rules.general.deterministic.architecture.r0014 import abstraction_nothing_depends_on
from tests.conftest import BINARY, needs_kernel

if TYPE_CHECKING:
    from pathlib import Path

SOURCES = {
    "tsconfig.json": '{\n  // the framework writes this one\n  "compilerOptions": {\n'
    '    "paths": { "$lib": ["src/lib"], "$lib/*": ["src/lib/*"] },\n  },\n}\n',
    "src/lib/models.ts": "export interface Shape {\n"
    "  area: number;\n"
    "}\n\n"
    "export class Circle implements Shape {\n"
    "  area = 1;\n\n"
    "  grow(step: number, factor = 2) {\n"
    "    return this.area * step * factor;\n"
    "  }\n"
    "}\n",
    "src/lib/index.ts": "export { Circle, Shape } from './models';\n",
    "src/api.ts": "import { Circle } from '$lib';\n"
    "import { z } from 'zod';\n"
    "import Panel from './Panel.svelte';\n\n"
    "export function build(): Circle {\n"
    "  return new Circle();\n"
    "}\n\n"
    "export const schema = z.object(Panel);\n",
}


@pytest.fixture(scope="session")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write one small TypeScript project every consumer below reads the same way."""
    root = tmp_path_factory.mktemp("typescript")
    for relative, source in SOURCES.items():
        written = root / relative
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(source)
    return root


@pytest.fixture(scope="session")
def graph(project: Path) -> RepositoryGraph:
    """Read the repository graph the kernel builds for that project."""
    return GraphReader(binary=BINARY, root=project).read()


@pytest.fixture(scope="session")
def coupling(project: Path) -> list[ModuleCouplingFact]:
    """Build the module coupling family the architecture rules read."""
    workspace = Kernel(binary=BINARY, root=project).build(
        ["ModuleCouplingFact"], {"ModuleCouplingFact": ModuleCouplingFact}
    )
    return workspace.stream(ModuleCouplingFact)


def module(facts: list[ModuleCouplingFact], name: str) -> ModuleCouplingFact:
    """Return one module's coupling fact by the name the graph gives it."""
    return next(fact for fact in facts if fact.module == name)


@needs_kernel
def test_the_graph_holds_every_typescript_declaration_the_project_states(
    graph: RepositoryGraph,
) -> None:
    """A TypeScript file reaches the graph as modules, types, callables, and parameters."""
    kinds = {
        kind: sorted(
            node.qualname
            for node in graph.nodes
            if node.kind is kind and node.language is Language.TYPESCRIPT
        )
        for kind in (NodeKind.MODULE, NodeKind.CLASS, NodeKind.METHOD, NodeKind.PARAMETER)
    }

    assert kinds[NodeKind.MODULE] == ["src/api", "src/lib/index", "src/lib/models"]
    assert kinds[NodeKind.CLASS] == ["src/lib/models.Circle", "src/lib/models.Shape"]
    assert kinds[NodeKind.METHOD] == ["src/lib/models.Circle.grow"]
    assert kinds[NodeKind.PARAMETER] == [
        "src/lib/models.Circle.grow.factor",
        "src/lib/models.Circle.grow.step",
    ]


@needs_kernel
def test_a_parameter_states_how_it_binds_and_whether_a_caller_may_leave_it_out(
    graph: RepositoryGraph,
) -> None:
    """`factor = 2` is a position a caller may skip and `step` is one it must fill."""
    parameters = {node.qualname: node for node in graph.nodes if node.kind is NodeKind.PARAMETER}

    assert parameters["src/lib/models.Circle.grow.step"].ordinal == 0
    assert not parameters["src/lib/models.Circle.grow.step"].has_default
    assert parameters["src/lib/models.Circle.grow.factor"].ordinal == 1
    assert parameters["src/lib/models.Circle.grow.factor"].has_default


@needs_kernel
def test_an_import_reaches_the_module_that_declares_the_symbol(graph: RepositoryGraph) -> None:
    """The alias reaches the barrel and the barrel's re-export reaches what defines the class."""
    modules = graph.of_kind(NodeKind.MODULE)
    reached = sorted(
        modules[edge.target].qualname
        for edge in graph.edges
        if edge.kind is EdgeKind.IMPORT and edge.path == "src/api.ts" and edge.target in modules
    )

    assert reached == ["src/lib/models"]


@needs_kernel
def test_what_no_static_reading_can_settle_stays_visible(graph: RepositoryGraph) -> None:
    """A component this kernel never parsed is unresolved rather than quietly dropped."""
    gaps = sorted(node.qualname for node in graph.nodes if node.kind is NodeKind.UNRESOLVED_SYMBOL)
    unresolved = {edge.resolution for edge in graph.edges if edge.target.endswith(gaps[0])}

    assert gaps == ["src/api::src/Panel.svelte"]
    assert unresolved == {Resolution.UNRESOLVED}


@needs_kernel
def test_a_package_the_project_installs_is_a_dependency_rather_than_a_gap(
    graph: RepositoryGraph,
) -> None:
    """A bare specifier names something outside the repository, which is not a gap in the graph."""
    outside = sorted(
        node.qualname for node in graph.nodes if node.kind is NodeKind.EXTERNAL_MODULE
    )

    assert outside == ["zod"]


@needs_kernel
def test_module_coupling_reports_every_typescript_module(
    coupling: list[ModuleCouplingFact],
) -> None:
    """`ModuleCouplingFact` covers TypeScript, which is what the architecture rules read."""
    assert sorted(fact.module for fact in coupling) == [
        "src/api",
        "src/lib/index",
        "src/lib/models",
    ]
    assert module(coupling, "src/lib/models").afferent_count == 2
    assert module(coupling, "src/api").efferent_count == 1


@needs_kernel
def test_abstractness_counts_the_contracts_typescript_states(
    coupling: list[ModuleCouplingFact],
) -> None:
    """An interface is a contract and a class implementing it is not."""
    models = module(coupling, "src/lib/models")

    assert models.declaration_count == 2
    assert models.abstract_declaration_count == 1


@needs_kernel
def test_the_architecture_rules_judge_a_typescript_module(
    coupling: list[ModuleCouplingFact],
) -> None:
    """Every rule reading the coupling family now has TypeScript evidence to judge."""
    models = module(coupling, "src/lib/models")

    assert dependency_on_a_less_stable_module(models).value == 0
    assert concrete_module_the_repository_leans_on(models).value is False
    assert abstraction_nothing_depends_on(models) is False


@needs_kernel
def test_the_class_diagram_draws_typescript_classes_and_their_members(
    graph: RepositoryGraph,
) -> None:
    """`mcmr diagram --kind class` sees the boxes, the members, and the inheritance line."""
    drawing = DiagramBuilder.of(DiagramKind.CLASS).build(graph)
    boxes = {node.key: node for node in drawing.nodes}

    assert sorted(boxes) == ["src/lib/models.Circle", "src/lib/models.Shape"]
    assert [
        (member.name, member.kind, member.visibility)
        for member in boxes["src/lib/models.Circle"].members
    ] == [
        ("area", MemberKind.ATTRIBUTE, Visibility.PUBLIC),
        ("grow", MemberKind.METHOD, Visibility.PUBLIC),
    ]
    assert [(edge.source, edge.target, edge.kind) for edge in drawing.edges] == [
        ("src/lib/models.Circle", "src/lib/models.Shape", RelationKind.INHERIT)
    ]


@needs_kernel
def test_the_package_diagram_draws_typescript_modules_and_their_imports(
    graph: RepositoryGraph,
) -> None:
    """`mcmr diagram --kind package` sees every module and the arrow between two of them."""
    drawing = DiagramBuilder.of(DiagramKind.PACKAGE).build(graph)

    assert [node.key for node in drawing.nodes] == ["src/api", "src/lib/index", "src/lib/models"]
    assert [(edge.source, edge.target) for edge in drawing.edges] == [
        ("src/api", "src/lib/models"),
        ("src/lib/index", "src/lib/models"),
    ]


@needs_kernel
def test_the_matrix_and_the_impact_set_hold_typescript_modules(
    graph: RepositoryGraph, project: Path
) -> None:
    """Both projections order and walk TypeScript modules the way they do Python ones."""
    projection = ModuleGraph.of(graph, project)
    matrix = projection.matrix()
    impact = projection.impact([project / "src" / "lib" / "models.ts"])

    assert set(matrix.ordering) == {"src/api", "src/lib/index", "src/lib/models"}
    assert matrix.cycles == ()
    assert matrix.back_edges == ()
    assert impact.changed == ("src/lib/models",)
    assert sorted(reached.module for reached in impact.reached) == ["src/api", "src/lib/index"]


@needs_kernel
def test_override_facts_report_typescript_inheritance(project: Path) -> None:
    """`OverrideFact` pairs a class with the interface it implements and states both signatures."""
    workspace = Kernel(binary=BINARY, root=project).build(
        ["OverrideFact"], {"OverrideFact": OverrideFact}
    )
    pairs = workspace.stream(OverrideFact)
    grow = next(member for member in pairs[0].declared if member.name == "grow")

    assert [(fact.derived, fact.base) for fact in pairs] == [
        ("src/lib/models.Circle", "src/lib/models.Shape")
    ]
    assert grow.parameters is not None
    assert [(held.name, held.has_default) for held in grow.parameters] == [
        ("step", False),
        ("factor", True),
    ]
