from typing import TYPE_CHECKING

from ..kinds import DiagramFormat
from ..relations import RelationKind
from .base import DiagramRenderer

if TYPE_CHECKING:
    from ..models import Diagram, DiagramNode, Member


class D2Renderer(DiagramRenderer):
    """Render a diagram in D2 class notation."""

    notation = DiagramFormat.D2

    def arrow(self, kind: RelationKind) -> str:
        """Return the D2 label for one relation."""
        return "inherits" if kind is RelationKind.INHERIT else "imports"

    def render(self, diagram: Diagram) -> str:
        """Return one class shape per box and one labeled connection per line."""
        shapes = [self.shape(node) for node in diagram.nodes]
        connections = [
            f'"{edge.source}" -> "{edge.target}": {self.arrow(edge.kind)}'
            for edge in diagram.edges
        ]
        return "\n".join([f"# {diagram.title}", *shapes, *connections]) + "\n"

    def row(self, member: Member) -> str:
        """Return one member row with the D2 comment sigil escaped."""
        marker = "\\#" if member.marker == "#" else member.marker
        return f"{marker}{member.signature()}"

    def shape(self, node: DiagramNode) -> str:
        """Return one D2 class shape."""
        rows = [
            f'"{node.key}": {{',
            f"  label: {node.label}",
            "  shape: class",
            *(f"  {self.row(member)}" for member in node.members),
            "}",
        ]
        return "\n".join(rows)
