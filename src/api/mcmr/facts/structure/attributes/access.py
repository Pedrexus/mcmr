from typing import TYPE_CHECKING

from .groups import AttributeAccessFields

if TYPE_CHECKING:
    from ...foundation import NodeRef


class AttributeAccess(AttributeAccessFields):
    """Retain one member access, its visibility, and owner relationship."""

    receiver_type_bases: list[str] = []
    node: NodeRef
