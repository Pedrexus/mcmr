import re
from pathlib import Path

import pytest

from mcmr.kernel import locate
from mcmr.repository import (
    GraphReader,
    RepositoryGraph,
)
from mcmr.structure.diagrams import (
    ClassDiagram,
    DiagramBuilder,
    DiagramFormat,
    DiagramKind,
    DiagramRenderer,
    MemberKind,
    PackageDiagram,
)

_PACKAGE = Path(__file__).parents[2]

pytestmark = pytest.mark.skipif(
    not locate(_PACKAGE).exists(),
    reason="the diagram oracle needs the kernel binary this checkout builds",
)

# One box of a Pyreverse dot file and one line between two of them. Both diagrams it writes use
# the same two shapes, so reading either one needs nothing more than these.
_BOX = re.compile(r'^"(?P<key>[^"]+)" \[.*label=<(?P<label>.*)>, shape=')
_ARROW = re.compile(r'^"(?P<source>[^"]+)" -> "(?P<target>[^"]+)"')
_ROW = '<br ALIGN="LEFT"/>'


def boxes(dot: str) -> set[str]:
    """Return the name of every box one Pyreverse diagram draws."""
    return {match["key"] for line in dot.splitlines() if (match := _BOX.match(line))}


def arrows(dot: str) -> set[tuple[str, str]]:
    """Return every line one Pyreverse diagram draws, as the pair of boxes it joins."""
    return {
        (match["source"], match["target"])
        for line in dot.splitlines()
        if (match := _ARROW.match(line))
    }


def compartments(dot: str) -> dict[str, list[set[str]]]:
    """Return the attributes and methods Pyreverse gives each class, keyed by class name."""
    found = {}
    for line in dot.splitlines():
        if match := _BOX.match(line):
            attributes, methods = match["label"].strip("{}").split("|")[1:]
            found[match["key"]] = [names(attributes, cut=" : "), names(methods, cut="(")]
    return found


def names(compartment: str, *, cut: str) -> set[str]:
    """Return member names in one compartment without types or argument lists."""
    return {entry.split(cut)[0].strip() for entry in compartment.split(_ROW) if entry.strip()}


def test_the_class_diagram_holds_what_pyreverse_holds(
    graph: RepositoryGraph, drawings: Path
) -> None:
    """Pyreverse is the oracle for the classes, the inheritance between them, and their members.

    The fixture states what it expects Pyreverse to find, so a run where Pyreverse read nothing at
    all is a failure rather than two empty answers agreeing with each other.
    """
    held = compartments(dot := (drawings / "classes.dot").read_text())
    drawn = ClassDiagram().build(graph)

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
        attributes = {
            member.name for member in node.members if member.kind is MemberKind.ATTRIBUTE
        }
        methods = {member.name for member in node.members if member.kind is MemberKind.METHOD}
        assert [attributes, methods] == held[node.key], node.key


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
    reader = GraphReader(binary=locate(_PACKAGE), root=repository)
    first, second = reader.read(), reader.read()

    for kind in DiagramKind:
        for notation in DiagramFormat:
            renderer = DiagramRenderer.of(notation)
            builder = DiagramBuilder.of(kind)
            rendered = renderer.render(builder.build(first))
            assert rendered == renderer.render(builder.build(second))
            assert rendered.splitlines()
