from enum import StrEnum

import polars as pl
from patos import FrozenModel, Runtime

from ...domain.contracts import Criterion
from .definitions import DecisionTable, ModelMode


class ModelQueryFields[Category: StrEnum = StrEnum](FrozenModel):
    """Retain a contextual candidate relation and its decision contract."""

    candidates: Runtime[pl.LazyFrame]
    category: type[Category]
    instructions: str
    mode: ModelMode
    criteria: list[Criterion] = []
    decision_table: DecisionTable[Category] = []
    default: Category | None = None
