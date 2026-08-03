from typing import TYPE_CHECKING

from .groups import TypeAnnotationFields

if TYPE_CHECKING:
    from typing import Literal

    from ...foundation import NodeRef


class TypeAnnotation(TypeAnnotationFields):
    """Retain one resolved annotation and reusable constraint recipe."""

    is_field_specific_metadata: bool = False
    role: Literal["alias", "parameter", "return", "variable"] = "variable"
    is_external_boundary: bool = False
    node: NodeRef | None = None
