from enum import StrEnum
from typing import TYPE_CHECKING

import polars as pl

from mcmr.domain.contracts import RuleValue
from mcmr.query import RuleQuery

if TYPE_CHECKING:
    from mcmr.execution.queries import ModelQuery

from ..first import FirstCategoryBackend


class NoFindingsBackend(FirstCategoryBackend):
    """Resolve a valid category while deliberately omitting model provenance."""

    async def resolve[Category: StrEnum](
        self,
        query: ModelQuery[Category],
    ) -> RuleQuery[RuleValue]:
        resolved: RuleQuery[str] = RuleQuery.category(
            query.candidates,
            pl.lit(str(next(iter(query.category)))),
        )
        return RuleQuery[RuleValue](values=resolved.values)
