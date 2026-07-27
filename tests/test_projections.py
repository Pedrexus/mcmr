import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mcmr.cli import impact as impact_command
from mcmr.cli import imports
from mcmr.cli import matrix as matrix_command
from mcmr.projections import (
    Dependency,
    ImpactText,
    JsonRendering,
    MatrixText,
    ModuleGraph,
    ProjectionFormat,
)
from mcmr.repository import (
    EdgeKind,
    GraphNode,
    GraphReader,
    GraphRelation,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from tests.conftest import BINARY, ROOT, needs_kernel

ARCHY = Path(__file__).parents[2] / "archy"
SOURCE = ROOT / "src"

needs_archy = pytest.mark.skipif(
    not (ARCHY / "pyproject.toml").exists() or shutil.which("uv") is None,
    reason="the graph oracle needs the Archy checkout and uv",
)


@pytest.fixture(scope="session")
def snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy this project's own source so both producers read exactly the same bytes.

    A comparison against an oracle is only a comparison when the two readers see one tree, so
    the checkout is copied once and MCMR and Archy are both pointed at the copy.
    """
    copied = tmp_path_factory.mktemp("oracle") / "src"
    shutil.copytree(SOURCE, copied, ignore=shutil.ignore_patterns("__pycache__"))
    return copied


def chain() -> ModuleGraph:
    """Build a layered repository by hand, where `a` imports `b` imports `c`."""
    return ModuleGraph(
        root=Path("/repository"),
        paths={"pkg": "pkg/__init__.py", **{f"pkg.{name}": f"pkg/{name}.py" for name in "abc"}},
        dependencies=(
            Dependency(importer="pkg.a", imported="pkg.b", path="pkg/a.py", lines=(1,)),
            Dependency(importer="pkg.b", imported="pkg.c", path="pkg/b.py", lines=(1, 4)),
        ),
    )


def tangle() -> ModuleGraph:
    """Build a repository whose `a`, `b`, and `c` import each other, with `e` above them."""
    return ModuleGraph(
        root=Path("/repository"),
        paths={f"pkg.{name}": f"pkg/{name}.py" for name in "abcde"},
        dependencies=(
            Dependency(importer="pkg.a", imported="pkg.b", path="pkg/a.py", lines=(1,)),
            Dependency(importer="pkg.b", imported="pkg.c", path="pkg/b.py", lines=(1,)),
            Dependency(importer="pkg.c", imported="pkg.a", path="pkg/c.py", lines=(1,)),
            Dependency(importer="pkg.c", imported="pkg.d", path="pkg/c.py", lines=(2,)),
            Dependency(importer="pkg.e", imported="pkg.a", path="pkg/e.py", lines=(1,)),
        ),
    )


def repository(tmp_path: Path) -> Path:
    """Write one small package whose imports form a layering, and return its root."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "engine.py").write_text(
        "from .store import load\n\n\ndef run():\n    return load()\n"
    )
    (package / "store.py").write_text("import json\n\n\ndef load():\n    return json.dumps({})\n")
    (package / "cli.py").write_text("from .engine import run\n\n\ndef main():\n    return run()\n")
    return tmp_path


def archy_output(*arguments: str) -> str:
    """Return what one Archy command prints, from the fork this monorepo checked out."""
    completed = subprocess.run(
        ["uv", "run", "--quiet", "--extra", "parser", "archy", *arguments],
        cwd=ARCHY,
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return completed.stdout


def archy_matrix(root: Path) -> tuple[set[str], set[tuple[str, str]]]:
    """Return the modules and the dependency pairs Archy's own matrix states, by name."""
    payload = json.loads(
        archy_output("dsm", str(root), "--group", "topological", "--format", "json")
    )
    ordering: list[str] = payload["ordering"]
    return set(ordering), {
        (ordering[cell["row"]], ordering[cell["col"]]) for cell in payload["cells"]
    }


def archy_impact(root: Path, changed: list[Path]) -> tuple[set[str], set[str]]:
    """Return the changed modules and the impacted modules Archy names for one edit."""
    files = [argument for path in changed for argument in ("--file", str(path))]
    payload = json.loads(archy_output("impact", str(root), *files, "--format", "json"))
    changed_modules: list[str] = payload["changed"]
    impacted: list[str] = payload["impacted"]
    return set(changed_modules), set(impacted)


def type_only_dependencies(root: Path, modules: set[str]) -> set[tuple[str, str]]:
    """Return the module pairs a repository states only inside a `TYPE_CHECKING` block.

    MCMR leaves those imports out of the graph on purpose, because they do not exist when the
    program runs, so this is what tells the deliberate difference from the oracle apart from a
    defect. It reads the source directly rather than asking either producer.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = module if parts[-1] == "__init__" else module.rsplit(".", 1)[0]
        for guard in ast.walk(ast.parse(path.read_text())):
            if not isinstance(guard, ast.If) or not guards_types(guard.test):
                continue
            for statement in ast.walk(guard):
                if isinstance(statement, ast.ImportFrom):
                    imported = resolved(statement, package)
                    if imported in modules:
                        found.add((module, imported))
    return found


def guards_types(test: ast.expr) -> bool:
    """Whether one `if` test is the `TYPE_CHECKING` guard, spelled either way."""
    return any(
        (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING")
        or (isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING")
        for node in ast.walk(test)
    )


def resolved(statement: ast.ImportFrom, package: str) -> str:
    """Return the module one import names, resolving a relative one against its own package."""
    if not statement.level:
        return statement.module or ""
    owner = package.split(".")
    kept = owner[: len(owner) - statement.level + 1]
    return ".".join([*kept, statement.module] if statement.module else kept)


def test_the_matrix_orders_every_importer_ahead_of_what_it_imports() -> None:
    """A layering has no dependency below the diagonal, which is the whole point of the order."""
    projection = chain().matrix()

    assert projection.ordering == ("pkg", "pkg.a", "pkg.b", "pkg.c")
    assert [(cell.row, cell.column) for cell in projection.cells] == [(1, 2), (2, 3)]
    assert projection.cycles == ()
    assert projection.back_edges == ()


def test_a_cycle_travels_as_one_position_and_names_the_dependency_pointing_back() -> None:
    """Modules that import each other cannot be ordered, so the matrix says so out loud."""
    projection = tangle().matrix()

    assert projection.ordering == ("pkg.e", "pkg.a", "pkg.b", "pkg.c", "pkg.d")
    assert [cycle.members for cycle in projection.cycles] == [("pkg.a", "pkg.b", "pkg.c")]
    assert [(edge.importer, edge.imported) for edge in projection.back_edges] == [
        ("pkg.c", "pkg.a")
    ]
    assert projection.back_edges[0].location() == "pkg/c.py:1"


def test_a_module_that_two_others_import_waits_for_both_of_them() -> None:
    """A module takes its position only once every importer of it has one, which is a layering."""
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

    assert projection.ordering == ("api", "left", "right", "core")
    assert projection.back_edges == ()


def test_the_impact_set_names_what_reaches_a_change_and_how_far_away_it_is() -> None:
    """The answer to what an edit could break is every module with an import path to it."""
    projection = tangle().impact([Path("/repository/pkg/d.py")])

    assert projection.changed == ("pkg.d",)
    assert [(item.module, item.distance) for item in projection.reached] == [
        ("pkg.c", 1),
        ("pkg.b", 2),
        ("pkg.a", 3),
        ("pkg.e", 4),
    ]
    assert projection.unresolved == ()


def test_a_change_to_several_files_is_one_walk_and_never_reports_itself() -> None:
    """Two changed files share one traversal, and neither is its own blast radius."""
    projection = chain().impact([Path("/repository/pkg/c.py"), Path("/repository/pkg/b.py")])

    assert projection.changed == ("pkg.b", "pkg.c")
    assert [(item.module, item.distance) for item in projection.reached] == [("pkg.a", 1)]


def test_a_changed_path_no_module_owns_is_reported_rather_than_dropped() -> None:
    """A file outside the graph would otherwise read as a change nothing depends on."""
    projection = chain().impact([Path("/repository/notes.md")])

    assert projection.changed == ()
    assert projection.unresolved == ("/repository/notes.md",)
    assert projection.reached == ()


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
    assert projection.dependencies == (
        Dependency(importer="pkg.a", imported="pkg.b", path="a.py", lines=(1, 3)),
    )


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
        dependencies=tuple(
            Dependency(importer=importer, imported=imported, path=f"{importer}.py", lines=(1,))
            for importer in "abc"
            for imported in "abc"
            if importer != imported
        ),
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
    graph = imports(root, "", BINARY)

    assert set(graph.paths) == {"pkg", "pkg.cli", "pkg.engine", "pkg.store"}
    assert [(edge.importer, edge.imported) for edge in graph.dependencies] == [
        ("pkg.cli", "pkg.engine"),
        ("pkg.engine", "pkg.store"),
    ]
    assert graph.matrix().ordering == ("pkg", "pkg.cli", "pkg.engine", "pkg.store")
    assert [item.module for item in graph.impact([root / "pkg" / "store.py"]).reached] == [
        "pkg.engine",
        "pkg.cli",
    ]


@needs_kernel
def test_two_runs_over_unchanged_source_render_the_same_text(tmp_path: Path) -> None:
    """A projection a reader diffs across commits has to be stable when nothing moved."""
    root = repository(tmp_path)
    runs = [ModuleGraph.of(GraphReader(binary=BINARY, root=root).read(), root) for _ in range(2)]
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

    matrix_command(root, kernel=BINARY)
    assert "Design structure matrix over 4 modules and 2 dependencies" in capsys.readouterr().out

    matrix_command(root, format=ProjectionFormat.JSON, exclude="**/cli.py", kernel=BINARY)
    written = json.loads(capsys.readouterr().out)
    assert written["ordering"] == ["pkg", "pkg.engine", "pkg.store"]


@needs_kernel
def test_the_impact_command_reports_what_a_change_could_break(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr impact` takes the changed paths a commit touched and answers over the graph."""
    root = repository(tmp_path)

    impact_command(root, changed=f"{root / 'pkg' / 'store.py'}, ", kernel=BINARY)
    assert "1 changed, 2 modules reach them through imports" in capsys.readouterr().out

    impact_command(
        root, changed=str(root / "pkg" / "store.py"), format=ProjectionFormat.JSON, kernel=BINARY
    )
    written = json.loads(capsys.readouterr().out)
    assert [item["module"] for item in written["reached"]] == ["pkg.engine", "pkg.cli"]


@needs_kernel
@needs_archy
def test_the_matrix_agrees_with_the_archy_oracle_on_this_repository(snapshot: Path) -> None:
    """Archy implements the same projection, so its answer is the one MCMR owes.

    The modules and the dependencies have to be the same set on real source. One difference is
    deliberate and pinned here rather than papered over. MCMR leaves a `TYPE_CHECKING` import
    out of the graph, because it does not exist when the program runs, and Archy counts it, so
    every pair the oracle has and MCMR does not must be one of those.
    """
    ours = imports(snapshot, "", BINARY)
    our_pairs = {(edge.importer, edge.imported) for edge in ours.dependencies}
    their_modules, their_pairs = archy_matrix(snapshot)
    type_only = type_only_dependencies(snapshot, set(ours.paths))

    assert set(ours.paths) == their_modules
    assert our_pairs <= their_pairs
    assert their_pairs - our_pairs == type_only - our_pairs
    assert type_only


@needs_kernel
@needs_archy
def test_the_impact_set_agrees_with_the_archy_oracle_on_this_repository(snapshot: Path) -> None:
    """The same blast radius, over a change whose reach no `TYPE_CHECKING` import decides."""
    ours = imports(snapshot, "", BINARY)
    changed = [snapshot / "mcmr" / "bases.py"]
    projection = ours.impact(changed)
    their_changed, their_impacted = archy_impact(snapshot, changed)

    assert set(projection.changed) == their_changed
    assert {item.module for item in projection.reached} == their_impacted

    pair = [snapshot / "mcmr" / "bases.py", snapshot / "mcmr" / "policy.py"]
    together = ours.impact(pair)
    their_changed, their_impacted = archy_impact(snapshot, pair)

    assert set(together.changed) == their_changed
    assert {item.module for item in together.reached} == their_impacted


@needs_kernel
@needs_archy
def test_a_type_checking_import_is_the_whole_difference_from_the_oracle(snapshot: Path) -> None:
    """MCMR plus the imports that never run is Archy exactly, which pins the one difference.

    A module reached only through a `TYPE_CHECKING` import is not in the blast radius, because
    that import does not exist when the program runs, and Archy counts it anyway. Putting those
    edges back has to reproduce the oracle answer, or the difference is a defect rather than a
    decision. Both walks are the same traversal, which the exact agreement above already checks.
    """
    ours = imports(snapshot, "", BINARY)
    our_pairs = {(edge.importer, edge.imported) for edge in ours.dependencies}
    missing = sorted(type_only_dependencies(snapshot, set(ours.paths)) - our_pairs)
    widened = ModuleGraph(
        root=snapshot,
        paths=ours.paths,
        dependencies=ours.dependencies
        + tuple(
            Dependency(importer=importer, imported=imported, path=ours.paths[importer])
            for importer, imported in missing
        ),
    )
    changed = [snapshot / "mcmr" / "models.py"]
    reached = {item.module for item in ours.impact(changed).reached}
    _, their_impacted = archy_impact(snapshot, changed)

    assert missing
    assert reached <= their_impacted
    assert {item.module for item in widened.impact(changed).reached} == their_impacted
