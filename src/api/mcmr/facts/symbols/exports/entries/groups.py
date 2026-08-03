from patos import FrozenModel
from pydantic import PositiveInt

from .....domain.primitives import NonEmptyStr
from ....foundation import NodeRef


class ExportBypassFields(FrozenModel):
    """Retain bypass identity, replacement, and binding evidence."""

    public_module: NonEmptyStr
    name: NonEmptyStr
    target: NonEmptyStr
    expression: NonEmptyStr
    module_node: NodeRef | None = None
    replacement_module: str | None = None
    binding_count: PositiveInt = 1
