from enum import StrEnum, auto

import polars as pl

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ModuleCouplingFact
from ......table import GenericRelation, Table


class _ComponentBalance(StrEnum):
    BALANCED = auto()
    OVERSIZED = auto()
    FRAGMENTED = auto()
    ASYMMETRIC = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1007",
    policy=Category.outcomes(
        _ComponentBalance, good={_ComponentBalance.BALANCED}, neutral={_ComponentBalance.UNCERTAIN}
    ),
)
def component_balance(
    subject: Table[ModuleCouplingFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ComponentBalance]:
    """Judge whether component boundaries create a maintainable size distribution.

    Definition
    ----------
    Compare source volume, public surface, responsibilities, dependencies, churn, navigation,
    and ownership across peer packages. Size is evidence rather than an automatic violation.
    The criteria separately establish coherence, concentrated work, navigation cost, and a
    deliberate reason for asymmetric size.

    Evidence
    --------
    Findings cite component metrics, responsibilities, edges, changes, and navigation costs.

    Exceptions
    ----------
    Generated components and intentionally thin adapters may be asymmetric.

    Examples
    --------
    One package owning most unrelated application behavior is `oversized`. Splitting every small
    value type into a package can be `fragmented`.

    References
    ----------
    Cites "Building Maintainable Software", balance component size
    Cites "A Philosophy of Software Design", deep modules
    Cites "Clean Architecture"
    """
    query = backend.classification(
        subject,
        category=_ComponentBalance,
        instructions=component_balance.instructions,
    )
    available = set(subject.lazy(GenericRelation.FACTS).collect_schema().names())
    fields = {
        "module",
        "declaration_count",
        "abstract_declaration_count",
        "afferent_count",
        "efferent_count",
    }
    if not fields.issubset(available):
        return query
    facts = subject.lazy(GenericRelation.FACTS)
    summary = facts.select(
        pl.col("fact_order").first(),
        pl.lit("component-balance:repository").alias("fact_id"),
        pl.col("path").first(),
        pl.col("start_line").first(),
        pl.col("start_column").first(),
        pl.col("end_line").first(),
        pl.col("end_column").first(),
        pl.col("language").first(),
        pl.len().cast(pl.UInt64).alias("component_count"),
        pl.struct(*sorted(fields)).implode().alias("components"),
    )
    return query.project(summary, fields=("component_count", "components"))
