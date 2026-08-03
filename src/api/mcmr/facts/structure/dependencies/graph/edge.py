from typing import TYPE_CHECKING

from ....foundation import Relation

if TYPE_CHECKING:
    from pydantic import NonNegativeInt, PositiveInt


class DependencyEdge(Relation):
    """Retain one resolved import between repository-owned modules."""

    path: str = ""
    line: PositiveInt = 1
    source_component: NonNegativeInt = 0
    target_component: NonNegativeInt = 0
