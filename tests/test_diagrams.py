import re
import subprocess
from pathlib import Path

import pytest

from mcmr.cli import diagram
from mcmr.diagrams import (
    ClassDiagram,
    D2Renderer,
    DiagramBuilder,
    DiagramFormat,
    DiagramKind,
    DiagramRenderer,
    MemberKind,
    MermaidRenderer,
    PackageDiagram,
)
from mcmr.kernel import locate
from mcmr.repository import (
    GraphNode,
    GraphReader,
    Language,
    NodeKind,
    RepositoryGraph,
)

pytestmark = pytest.mark.skipif(
    not locate(Path(__file__).parents[1]).exists(),
    reason="the diagram oracle needs the kernel binary this checkout builds",
)

# One box of a Pyreverse dot file and one line between two of them. Both diagrams it writes use
# the same two shapes, so reading either one needs nothing more than these.
BOX = re.compile(r'^"(?P<key>[^"]+)" \[.*label=<(?P<label>.*)>, shape=')
ARROW = re.compile(r'^"(?P<source>[^"]+)" -> "(?P<target>[^"]+)"')
ROW = '<br ALIGN="LEFT"/>'


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write one package both readers agree on, so a mismatch is a real disagreement.

    Everything here is stated in the source rather than inferred from it. An enum member, a
    dataclass field, and a base from the standard library all reach Pyreverse through inference
    that MCMR has no engine for, so a fixture holding one would be measuring the inference rather
    than the diagram. The nested class is here because both readers draw it as a box of its own
    rather than as a member of the class holding it, which is easy to get wrong.
    """
    root = tmp_path_factory.mktemp("diagrams")
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(
        "class Item:\n"
        '    label = "item"\n'
        "\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "        self._cost = 0\n"
        '        self.__token = "opaque"\n'
        "\n"
        "    @property\n"
        "    def cost(self):\n"
        "        return self._cost\n"
        "\n"
        "    def render(self):\n"
        "        return self.name\n"
        "\n"
        "    class Tag:\n"
        "        pass\n"
        "\n"
        "\n"
        "class Priced:\n"
        "    def price(self):\n"
        "        return 0\n"
        "\n"
        "\n"
        "class Book(Item, Priced):\n"
        "    def render(self):\n"
        "        return self.name.upper()\n"
        "\n"
        "    def _shelve(self):\n"
        "        return True\n"
    )
    (package / "api.py").write_text(
        "from .models import Book\n"
        "\n"
        "\n"
        "class Shelf(Book):\n"
        "    def stock(self):\n"
        "        return self.render()\n"
    )
    return root


@pytest.fixture(scope="module")
def drawings(repository: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the real Pyreverse over the fixture and return where its dot files landed.

    The dot files go outside the repository so that the tree MCMR reads holds only the source
    Pyreverse read, which is what makes a difference between the two a real difference.
    """
    output = tmp_path_factory.mktemp("pyreverse")
    subprocess.run(
        [
            "python",
            "-m",
            "pylint.pyreverse.main",
            "--output",
            "dot",
            "--output-directory",
            str(output),
            "--filter-mode",
            "ALL",
            "shop",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return output


@pytest.fixture(scope="module")
def graph(repository: Path) -> RepositoryGraph:
    """Return the repository graph the kernel builds over the same fixture."""
    return GraphReader(binary=locate(Path(__file__).parents[1]), root=repository).read()


def boxes(dot: str) -> frozenset[str]:
    """Return the name of every box one Pyreverse diagram draws."""
    return frozenset(match["key"] for line in dot.splitlines() if (match := BOX.match(line)))


def arrows(dot: str) -> frozenset[tuple[str, str]]:
    """Return every line one Pyreverse diagram draws, as the pair of boxes it joins."""
    return frozenset(
        (match["source"], match["target"])
        for line in dot.splitlines()
        if (match := ARROW.match(line))
    )


def compartments(dot: str) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """Return the attributes and the methods Pyreverse gives each class, keyed by class name."""
    found = {}
    for line in dot.splitlines():
        if match := BOX.match(line):
            attributes, methods = match["label"].strip("{}").split("|")[1:]
            found[match["key"]] = (names(attributes, " : "), names(methods, "("))
    return found


def names(compartment: str, cut: str) -> frozenset[str]:
    """Return the member names one compartment holds, dropping the type or the argument list."""
    return frozenset(
        entry.split(cut)[0].strip() for entry in compartment.split(ROW) if entry.strip()
    )


def executable(path: Path, script: str) -> Path:
    """Write one standing-in kernel, so a reader failing on it is the failure under test."""
    path.write_text(script)
    path.chmod(0o755)
    return path


def test_the_class_diagram_holds_what_pyreverse_holds(
    graph: RepositoryGraph, drawings: Path
) -> None:
    """Pyreverse is the oracle for the classes, the inheritance between them, and their members.

    The fixture states what it expects Pyreverse to find, so a run where Pyreverse read nothing at
    all is a failure rather than two empty answers agreeing with each other.
    """
    dot = (drawings / "classes.dot").read_text()
    drawn = ClassDiagram().build(graph)
    held = compartments(dot)

    assert boxes(dot) == {
        "shop.api.Shelf",
        "shop.models.Book",
        "shop.models.Item",
        "shop.models.Item.Tag",
        "shop.models.Priced",
    }
    assert {node.key for node in drawn.nodes} == boxes(dot)
    assert {(edge.source, edge.target) for edge in drawn.edges} == arrows(dot)
    assert len(arrows(dot)) == 3
    for node in drawn.nodes:
        attributes = frozenset(
            member.name for member in node.members if member.kind is MemberKind.ATTRIBUTE
        )
        methods = frozenset(
            member.name for member in node.members if member.kind is MemberKind.METHOD
        )
        assert (attributes, methods) == held[node.key], node.key


def test_the_package_diagram_holds_what_pyreverse_holds(
    graph: RepositoryGraph, drawings: Path
) -> None:
    """The modules and the imports between them are the whole of Pyreverse's package diagram."""
    dot = (drawings / "packages.dot").read_text()
    drawn = PackageDiagram().build(graph)

    assert boxes(dot) == {"shop", "shop.api", "shop.models"}
    assert arrows(dot) == {("shop.api", "shop.models")}
    assert {node.key for node in drawn.nodes} == boxes(dot)
    assert {(edge.source, edge.target) for edge in drawn.edges} == arrows(dot)


def test_a_member_carries_the_visibility_marker_pyreverse_only_computes(
    graph: RepositoryGraph,
) -> None:
    """Pyreverse sorts a name into four levels and prints none of them, and MCMR prints the sigil.

    This is the one place the two deliberately differ, so it is pinned rather than compared. Both
    readers agree that a leading underscore is protected and a leading double underscore is
    private, and a dunder is neither, so the UML marker follows from the level either way.
    """
    item = next(
        node for node in ClassDiagram().build(graph).nodes if node.key == "shop.models.Item"
    )

    assert {member.name: member.marker for member in item.members} == {
        "__token": "-",
        "_cost": "#",
        "cost": "+",
        "label": "+",
        "name": "+",
        "__init__": "+",
        "render": "+",
    }


def test_a_class_box_holds_its_attributes_before_its_methods(graph: RepositoryGraph) -> None:
    """UML reads top down, so the compartment order is part of the diagram rather than a detail."""
    item = next(
        node for node in ClassDiagram().build(graph).nodes if node.key == "shop.models.Item"
    )

    assert [member.signature() for member in item.members] == [
        "__token",
        "_cost",
        "cost",
        "label",
        "name",
        "__init__()",
        "render()",
    ]


def test_two_runs_over_unchanged_source_write_the_same_bytes(repository: Path) -> None:
    """A diagram nobody can diff is a diagram nobody can review, so ordering is a requirement."""
    reader = GraphReader(binary=locate(Path(__file__).parents[1]), root=repository)
    first, second = reader.read(), reader.read()

    for kind in DiagramKind:
        for notation in DiagramFormat:
            renderer = DiagramRenderer.of(notation)
            builder = DiagramBuilder.of(kind)
            rendered = renderer.render(builder.build(first))
            assert rendered == renderer.render(builder.build(second))
            assert rendered.splitlines()


def test_each_view_and_each_notation_answers_to_its_own_name() -> None:
    """The command line names a view and a notation, and nothing else resolves either."""
    assert isinstance(DiagramBuilder.of(DiagramKind.CLASS), ClassDiagram)
    assert isinstance(DiagramBuilder.of(DiagramKind.PACKAGE), PackageDiagram)
    assert isinstance(DiagramRenderer.of(DiagramFormat.D2), D2Renderer)
    assert isinstance(DiagramRenderer.of(DiagramFormat.MERMAID), MermaidRenderer)


def test_d2_writes_one_class_shape_per_box(graph: RepositoryGraph) -> None:
    """D2 takes the UML compartments as they are, once the comment sigil is escaped."""
    text = D2Renderer().render(ClassDiagram().build(graph))

    assert text.startswith("# classes\n")
    assert '"shop.models.Item": {\n  label: Item\n  shape: class\n' in text
    assert "\n  \\#_cost\n" in text
    assert "\n  +__init__()\n" in text
    assert '\n"shop.api.Shelf" -> "shop.models.Book": inherits\n' in text


def test_mermaid_writes_one_class_per_box(graph: RepositoryGraph) -> None:
    """Mermaid needs an identifier with no separator in it and reads a pair of underscores as
    emphasis, so the qualified name becomes the label and the members are escaped."""
    text = MermaidRenderer().render(ClassDiagram().build(graph))
    packages = MermaidRenderer().render(PackageDiagram().build(graph))

    assert text.startswith("---\ntitle: classes\n---\nclassDiagram\n")
    assert '\n  class shop_models_Item["Item"] {\n' in text
    assert "\n    +\\_\\_init\\_\\_()\n" in text
    assert "\n  shop_api_Shelf --|> shop_models_Book\n" in text
    assert "\n  shop_api --> shop_models\n" in packages


def test_a_node_is_named_by_the_separator_of_its_own_language() -> None:
    """A qualified name is spelled differently per language, and a path entity has no language."""
    declared = GraphNode(
        id="rust:class:kernel::graph::Node",
        kind=NodeKind.CLASS,
        qualname="kernel::graph::Node",
        language=Language.RUST,
    )
    placed = GraphNode(id="path:file:src/lib.rs", kind=NodeKind.FILE, qualname="src/lib.rs")

    assert declared.name == "Node"
    assert placed.name == "lib.rs"


def test_the_reader_drops_what_the_globs_exclude(tmp_path: Path) -> None:
    """A vendored tree is somebody else's design, so it never reaches the diagram."""
    (tmp_path / "kept.py").write_text("class Kept:\n    pass\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "dropped.py").write_text("class Dropped:\n    pass\n")

    reader = GraphReader(
        binary=locate(Path(__file__).parents[1]), root=tmp_path, exclude=("**/vendor/**",)
    )
    drawn = ClassDiagram().build(reader.read())

    assert {node.key for node in drawn.nodes} == {"kept.Kept"}


def test_the_reader_reports_a_kernel_that_failed(tmp_path: Path) -> None:
    """A kernel that could not answer is louder than an empty diagram that looks like an answer."""
    binary = executable(tmp_path / "failing", "#!/bin/sh\necho 'no such root' >&2\nexit 1\n")

    with pytest.raises(RuntimeError, match="no such root"):
        GraphReader(binary=binary, root=tmp_path).read()


def test_the_reader_refuses_a_kernel_speaking_another_protocol(tmp_path: Path) -> None:
    """A stale binary answering a newer request reads as a repository that lost its code."""
    binary = executable(
        tmp_path / "future", '#!/bin/sh\necho \'{"version": 99, "graph": {"nodes": []}}\'\n'
    )

    with pytest.raises(RuntimeError, match="protocol 99"):
        GraphReader(binary=binary, root=tmp_path).read()


def test_the_command_writes_the_diagram_it_was_asked_for(
    repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr diagram` writes one file and says what went into it."""
    output = tmp_path / "drawings" / "classes.d2"

    diagram(repository, kind=DiagramKind.CLASS, format=DiagramFormat.D2, output=output)

    assert '"shop.models.Item": {' in output.read_text()
    assert "5 boxes and 3 lines" in capsys.readouterr().out


def test_the_command_prints_the_diagram_when_no_file_is_named(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A diagram on standard output is what a pipe into another tool needs."""
    diagram(repository, kind=DiagramKind.PACKAGE, format=DiagramFormat.MERMAID)

    printed = capsys.readouterr().out
    assert "title: packages" in printed
    assert 'class shop_api["shop.api"]' in printed
