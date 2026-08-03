from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .operation import QueryOperation


class QueryFact(Fact):
    """Describe one resolved database query."""

    operations: list[QueryOperation] = []
