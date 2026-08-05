import polars as pl
from pydantic import PositiveInt

from ...... import rule
from ......facts import DataAssetFact, LineageEdgeFact
from ......query import CountQuery
from ......table import Table
from ..relations import detailed_count_query


def _downstream_reach(lineage: Table[LineageEdgeFact], depth: int) -> pl.LazyFrame:
    """Walk the lineage graph outward and count the distinct assets each asset feeds."""
    edges = lineage.records("edges").select("source", "target")
    frontier = edges.select("source", pl.col("target").alias("downstream"))
    reached = frontier
    for _ in range(depth - 1):
        frontier = frontier.join(
            edges,
            left_on="downstream",
            right_on="source",
            how="inner",
        ).select("source", pl.col("target").alias("downstream"))
        reached = pl.concat([reached, frontier])
    return (
        reached.filter(pl.col("source") != pl.col("downstream"))
        .unique(["source", "downstream"], maintain_order=True)
        .group_by("source", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("downstream_count"))
    )


@rule("ALL-DATA0011")
def unowned_high_impact_asset(
    subject: Table[DataAssetFact],
    lineage: Table[LineageEdgeFact],
    *,
    minimum_downstream: PositiveInt = 3,
    maximum_depth: PositiveInt = 3,
) -> CountQuery:
    """Count assets nobody owns that many downstream assets depend on.

    Definition
    ----------
    Walk the lineage graph outward from every asset, up to `maximum_depth` hops, count the distinct
    assets it reaches, and report an asset the catalog gives no owner when that count reaches
    `minimum_downstream`. Ownership is what turns a schema question into a conversation, and the
    assets that most need one are the ones a change propagates furthest from. An unowned leaf costs
    one team an afternoon while an unowned root stops a reporting stack.

    Impact is counted from the graph rather than guessed from a name. A table named `curated` may
    feed nothing while one named `scratch` feeds the whole warehouse, so the arrows say which is
    which and the naming convention says nothing.

    Evidence
    --------
    Each finding names the unowned asset and how many distinct assets sit downstream of it within
    the walked depth. The value is the number of unowned assets whose downstream reach meets the
    threshold.

    Exceptions
    ----------
    An asset naming any owner is never reported however far its lineage reaches, since this asks
    who answers rather than whether the answer is the right one. An asset whose reach falls under
    `minimum_downstream` stays quiet, which is what keeps a catalog of small unowned staging tables
    from drowning the roots that matter. An asset reachable only through a lineage edge the
    snapshot never recorded counts as unreached, so `ALL-DATA0010` is the rule that says whether
    this graph is complete enough to trust. A cycle contributes each asset once because the reach
    is a distinct set, and an asset never reaches itself.

    Examples
    --------
    An unowned `raw.orders` feeding `staging.orders`, which feeds `mart.revenue` and
    `mart.invoices`, reaches three assets and returns `1`. The same asset with one named owner
    returns `0`, and so does an unowned asset feeding only two others.

    References
    ----------
    Cites "OpenLineage specification", object model
    Cites "DAMA-DMBOK", data stewardship and accountability
    Cites "DataHub documentation", ownership and lineage metadata
    """
    reach = _downstream_reach(lineage, maximum_depth)
    selected = (
        subject.records("assets")
        .filter(pl.col("owners.length") == 0)
        .join(reach, left_on="identifier", right_on="source", how="inner")
        .filter(pl.col("downstream_count") >= minimum_downstream)
    )
    return detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("data asset `"),
            pl.col("identifier"),
            pl.lit("` has no owner and "),
            pl.col("downstream_count"),
            pl.lit(" downstream assets depend on it"),
        ),
        "unowned high impact asset",
    )
