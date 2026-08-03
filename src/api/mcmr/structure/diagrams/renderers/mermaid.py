import re
from typing import TYPE_CHECKING

from ..kinds import DiagramFormat
from ..relations import RelationKind
from .base import DiagramRenderer

if TYPE_CHECKING:
    from ..models import Diagram, DiagramNode, Member


class MermaidRenderer(DiagramRenderer):
    """Render a diagram in Mermaid class notation."""

    notation = DiagramFormat.MERMAID

    def arrow(self, kind: RelationKind) -> str:
        """Return the Mermaid operator for one relation."""
        return "--|>" if kind is RelationKind.INHERIT else "-->"

    def identifier(self, key: str) -> str:
        """Return one qualified name as a Mermaid identifier."""
        return re.sub(r"[^0-9A-Za-z_]", "_", key)

    def render(self, diagram: Diagram) -> str:
        """Return one class per box and one arrow per line."""
        classes = [self.shape(node) for node in diagram.nodes]
        arrows = [
            f"  {self.identifier(edge.source)} {self.arrow(edge.kind)} "
            f"{self.identifier(edge.target)}"
            for edge in diagram.edges
        ]
        header = ["---", f"title: {diagram.title}", "---", "classDiagram"]
        return "\n".join([*header, *classes, *arrows]) + "\n"

    def row(self, member: Member) -> str:
        """Return one member row with Mermaid emphasis escaped."""
        return f"{member.marker}{member.signature().replace('__', r'\_\_')}"

    def shape(self, node: DiagramNode) -> str:
        """Return one Mermaid class block."""
        rows = [
            f'  class {self.identifier(node.key)}["{node.label}"] {{',
            *(f"    {self.row(member)}" for member in node.members),
            "  }",
        ]
        return "\n".join(rows)
