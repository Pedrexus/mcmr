import json
from pathlib import Path
from typing import TYPE_CHECKING

from mcmr.commands.projection import impact as impact_command
from mcmr.commands.projection import imports
from mcmr.commands.projection import matrix as matrix_command
from mcmr.repository import (
    EdgeKind,
    GraphNode,
    GraphReader,
    GraphRelation,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from mcmr.structure.projections import (
    Dependency,
    ImpactText,
    JsonRendering,
    MatrixText,
    ModuleGraph,
    ProjectionFormat,
)

from ...support import kernel_binary, needs_kernel
from .support import chain, repository, tangle

if TYPE_CHECKING:
    import pytest


class TestModuleGraph:
    """Verify ordering and impact traversal over hand-built module graphs."""

    def test_a_cycle_travels_as_one_position_and_names_the_dependency_pointing_back(self) -> None:
        """Modules that import each other cannot be ordered, so the matrix says so out loud."""
        projection = tangle().matrix()

        assert projection.ordering == ["pkg.e", "pkg.a", "pkg.b", "pkg.c", "pkg.d"]
        assert [cycle.members for cycle in projection.cycles] == [["pkg.a", "pkg.b", "pkg.c"]]
        assert [(edge.importer, edge.imported) for edge in projection.back_edges] == [
            ("pkg.c", "pkg.a")
        ]
        assert projection.back_edges[0].location() == "pkg/c.py:1"

    def test_a_module_that_two_others_import_waits_for_both_of_them(self) -> None:
        """A module takes its position after every importer has one."""
        diamond = ModuleGraph(
            root=Path("/repository"),
            paths={name: f"{name}.py" for name in ("api", "left", "right", "core")},
            dependencies=(
                Dependency(importer="api", imported="left", path="api.py", lines=(1,)),
                Dependency(importer="api", imported="right", path="api.py", lines=(2,)),
                Dependency(importer="left", imported="core", path="left.py", lines=(1,)),
                Dependency(importer="right", imported="core", path="right.py", lines=(1,)),
            ),
        )

        projection = diamond.matrix()

        assert projection.ordering == ["api", "left", "right", "core"]
        assert projection.back_edges == []

    def test_the_impact_set_names_what_reaches_a_change_and_how_far_away_it_is(self) -> None:
        """The answer to what an edit could break is every module with an import path to it."""
        projection = tangle().impact([Path("/repository/pkg/d.py")])

        assert projection.changed == ["pkg.d"]
        assert [(item.module, item.distance) for item in projection.reached] == [
            ("pkg.c", 1),
            ("pkg.b", 2),
            ("pkg.a", 3),
            ("pkg.e", 4),
        ]
        assert projection.unresolved == []

    def test_the_matrix_orders_every_importer_ahead_of_what_it_imports(self) -> None:
        """A layering has no dependency below the diagonal."""
        projection = chain().matrix()

        assert projection.ordering == ["pkg", "pkg.a", "pkg.b", "pkg.c"]
        assert [(cell.row, cell.column) for cell in projection.cells] == [(1, 2), (2, 3)]
        assert projection.cycles == []
        assert projection.back_edges == []


def test_a_change_to_several_files_is_one_walk_and_never_reports_itself() -> None:
    """Two changed files share one traversal, and neither is its own blast radius."""
    projection = chain().impact([Path("/repository/pkg/c.py"), Path("/repository/pkg/b.py")])

    assert projection.changed == ["pkg.b", "pkg.c"]
    assert [(item.module, item.distance) for item in projection.reached] == [("pkg.a", 1)]


def test_a_changed_path_no_module_owns_is_reported_rather_than_dropped() -> None:
    """A file outside the graph would otherwise read as a change nothing depends on."""
    projection = chain().impact([Path("/repository/notes.md")])

    assert projection.changed == []
    assert projection.unresolved == ["/repository/notes.md"]
    assert projection.reached == []


def test_the_projection_keeps_the_modules_and_the_imports_and_nothing_else() -> None:
    """A design structure matrix is a statement about modules, so the rest of the graph goes."""
    graph = RepositoryGraph(
        nodes=(
            GraphNode(
                id="python:module:pkg.a", kind=NodeKind.MODULE, qualname="pkg.a", path="a.py"
            ),
            GraphNode(
                id="python:module:pkg.b", kind=NodeKind.MODULE, qualname="pkg.b", path="b.py"
            ),
            GraphNode(id="python:class:pkg.b.Store", kind=NodeKind.CLASS, qualname="pkg.b.Store"),
            GraphNode(
                id="python:external-module:json",
                kind=NodeKind.EXTERNAL_MODULE,
                qualname="json",
            ),
        ),
        edges=(
            GraphRelation(
                source="python:module:pkg.a",
                target="python:module:pkg.b",
                kind=EdgeKind.IMPORT,
                path="a.py",
                line=3,
                resolution=Resolution.EXACT,
            ),
            GraphRelation(
                source="python:module:pkg.a",
                target="python:module:pkg.b",
                kind=EdgeKind.IMPORT,
                path="a.py",
                line=1,
                resolution=Resolution.EXACT,
            ),
            GraphRelation(
                source="python:module:pkg.a",
                target="python:external-module:json",
                kind=EdgeKind.IMPORT,
                path="a.py",
                line=2,
                resolution=Resolution.EXTERNAL,
            ),
            GraphRelation(
                source="python:module:pkg.a",
                target="python:class:pkg.b.Store",
                kind=EdgeKind.INSTANTIATE,
                path="a.py",
                line=9,
                resolution=Resolution.EXACT,
            ),
        ),
    )

    projection = ModuleGraph.of(graph, Path("/repository"))

    assert projection.paths == {"pkg.a": "a.py", "pkg.b": "b.py"}
    assert projection.dependencies == [
        Dependency(importer="pkg.a", imported="pkg.b", path="a.py", lines=[1, 3]),
    ]


def test_the_text_matrix_draws_the_grid_and_lists_what_points_backwards() -> None:
    """The glyph says what a cell is, and the sections state the counts either way."""
    rendered = MatrixText().render(tangle().matrix())

    assert "Design structure matrix over 5 modules and 5 dependencies" in rendered
    assert "1 pkg.e" in rendered
    assert "4 . < . \\ X" in rendered
    assert "Cycles (1)\n  pkg.a pkg.b pkg.c" in rendered
    assert "Back edges (1)\n  pkg.c imports pkg.a at pkg/c.py:1" in rendered
    assert "Cycles (0)" in MatrixText().render(chain().matrix())


def test_the_text_matrix_bounds_the_grid_and_says_what_it_left_out() -> None:
    """A wide matrix is unreadable, so the rendering states its own truncation."""
    knot = ModuleGraph(
        root=Path("/repository"),
        paths={name: f"{name}.py" for name in "abc"},
        dependencies=[
            Dependency(importer=importer, imported=imported, path=f"{importer}.py", lines=[1])
            for importer in "abc"
            for imported in "abc"
            if importer != imported
        ],
    )

    assert "3 more modules follow these in the ordering" in MatrixText(limit=2).render(
        tangle().matrix()
    )
    assert "Back edges (3)" in MatrixText(limit=1).render(knot.matrix())
    assert "  and 2 more" in MatrixText(limit=1).render(knot.matrix())


def test_the_impact_text_states_the_change_and_what_reaches_it() -> None:
    """A reader wants the changed modules, the paths nothing owns, and the distance."""
    projection = chain().impact([Path("/repository/pkg/c.py"), Path("/repository/notes.md")])
    rendered = ImpactText().render(projection)

    assert "1 changed, 2 modules reach them through imports" in rendered
    assert "  changed pkg.c" in rendered
    assert "  unresolved /repository/notes.md" in rendered
    assert "   1  pkg.b  pkg/b.py" in rendered
    assert "   2  pkg.a  pkg/a.py" in rendered


def test_the_format_chooses_the_rendering_for_either_projection() -> None:
    """A new format is a member and a class of its own, never a change to the traversal."""
    graph = chain()
    projection = graph.matrix()
    written = json.loads(ProjectionFormat.JSON.matrix(32).render(projection))

    assert written["ordering"] == list(projection.ordering)
    assert isinstance(ProjectionFormat.TEXT.matrix(32), MatrixText)
    assert isinstance(ProjectionFormat.TEXT.impact(), ImpactText)
    assert isinstance(ProjectionFormat.JSON.impact(), JsonRendering)
    assert json.loads(
        ProjectionFormat.JSON.impact().render(graph.impact([Path("/repository/pkg/c.py")]))
    )["changed"] == ["pkg.c"]


@needs_kernel
def test_the_projections_read_a_real_repository_through_the_kernel(tmp_path: Path) -> None:
    """The graph the kernel builds is the only input either projection has."""
    root = repository(tmp_path)
    graph = imports(root, kernel_binary())

    assert set(graph.paths) == {"pkg", "pkg.cli", "pkg.engine", "pkg.store"}
    assert [(edge.importer, edge.imported) for edge in graph.dependencies] == [
        ("pkg.cli", "pkg.engine"),
        ("pkg.engine", "pkg.store"),
    ]
    assert graph.matrix().ordering == ["pkg", "pkg.cli", "pkg.engine", "pkg.store"]
    assert [item.module for item in graph.impact([root / "pkg" / "store.py"]).reached] == [
        "pkg.engine",
        "pkg.cli",
    ]


@needs_kernel
def test_two_runs_over_unchanged_source_render_the_same_text(tmp_path: Path) -> None:
    """A projection a reader diffs across commits has to be stable when nothing moved."""
    root = repository(tmp_path)
    runs = [
        ModuleGraph.of(GraphReader(binary=kernel_binary(), root=root).read(), root)
        for _ in range(2)
    ]
    changed = [root / "pkg" / "store.py"]

    assert MatrixText().render(runs[0].matrix()) == MatrixText().render(runs[1].matrix())
    assert JsonRendering().render(runs[0].matrix()) == JsonRendering().render(runs[1].matrix())
    assert ImpactText().render(runs[0].impact(changed)) == ImpactText().render(
        runs[1].impact(changed)
    )


@needs_kernel
def test_the_matrix_command_renders_a_grid_or_the_json_behind_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr matrix` is the way a reader asks for the projection."""
    root = repository(tmp_path)

    matrix_command(root, kernel=kernel_binary())
    assert "Design structure matrix over 4 modules and 2 dependencies" in capsys.readouterr().out

    (root / ".gitignore").write_text("pkg/cli.py\n")
    matrix_command(root, format=ProjectionFormat.JSON, kernel=kernel_binary())
    written = json.loads(capsys.readouterr().out)
    assert written["ordering"] == ["pkg", "pkg.engine", "pkg.store"]


@needs_kernel
def test_the_impact_command_reports_what_a_change_could_break(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr impact` takes the changed paths a commit touched and answers over the graph."""
    root = repository(tmp_path)

    impact_command(root, changed=f"{root / 'pkg' / 'store.py'}, ", kernel=kernel_binary())
    assert "1 changed, 2 modules reach them through imports" in capsys.readouterr().out

    impact_command(
        root,
        changed=str(root / "pkg" / "store.py"),
        format=ProjectionFormat.JSON,
        kernel=kernel_binary(),
    )
    written = json.loads(capsys.readouterr().out)
    assert [item["module"] for item in written["reached"]] == ["pkg.engine", "pkg.cli"]
