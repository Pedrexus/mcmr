from typing import TYPE_CHECKING

from .groups import QueryOperationFields

if TYPE_CHECKING:
    from ...foundation import NodeRef


class QueryOperation(QueryOperationFields):
    """Retain one resolved SQLAlchemy or SQLModel operation chain."""

    has_execution_options: bool = False
    node: NodeRef
    scalars_segment: NodeRef | None = None
    execute_segment: NodeRef | None = None
