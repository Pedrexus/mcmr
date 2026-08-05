from pathlib import Path

import pytest

from mcmr.commands.insight import diagram
from mcmr.project import locate
from mcmr.repository import (
    GraphNode,
    GraphReader,
    Language,
    NodeKind,
    RepositoryGraph,
)
from mcmr.structure.diagrams import (
    ClassDiagram,
    D2Renderer,
    DiagramBuilder,
    DiagramFormat,
    DiagramKind,
    DiagramRenderer,
    MermaidRenderer,
    PackageDiagram,
)

_PACKAGE = Path(__file__).parents[2]

pytestmark = pytest.mark.skipif(
    not locate(_PACKAGE).exists(),
    reason="the diagram oracle needs the kernel binary this checkout builds",
)


def executable(path: Path, script: str) -> Path:
    """Write one standing-in kernel, so its failure remains the failure under test."""
    path.write_text(script)
    path.chmod(0o755)
    return path


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
    """Render qualified labels and escape members in Mermaid class boxes.

    Mermaid needs an identifier with no separator in it and reads a pair of underscores as
    emphasis, so the qualified name becomes the label.
    """
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


def test_the_reader_drops_what_gitignore_excludes(tmp_path: Path) -> None:
    """A vendored tree is somebody else's design, so it never reaches the diagram."""
    (tmp_path / "kept.py").write_text("class Kept:\n    pass\n")
    (tmp_path / ".gitignore").write_text("vendor/\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "dropped.py").write_text("class Dropped:\n    pass\n")

    reader = GraphReader(binary=locate(_PACKAGE), root=tmp_path)
    drawn = ClassDiagram().build(reader.read())

    assert {node.key for node in drawn.nodes} == {"kept.Kept"}


def test_the_reader_reports_a_kernel_that_failed(tmp_path: Path) -> None:
    """A kernel that could not answer is louder than an empty diagram that looks like an answer."""
    binary = executable(
        tmp_path / "failing",
        "#!/bin/sh\necho 'no such root' >&2\nexit 1\n",
    )

    with pytest.raises(RuntimeError, match="no such root"):
        GraphReader(binary=binary, root=tmp_path).read()


def test_the_reader_refuses_a_kernel_speaking_another_protocol(tmp_path: Path) -> None:
    """A stale binary answering a newer request reads as a repository that lost its code."""
    binary = executable(
        tmp_path / "future",
        '#!/bin/sh\necho \'{"version": 99, "graph": {"nodes": []}}\'\n',
    )

    with pytest.raises(RuntimeError, match="protocol 99"):
        GraphReader(binary=binary, root=tmp_path).read()


def test_the_command_writes_the_diagram_it_was_asked_for(
    *, repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
