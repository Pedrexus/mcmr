import polars as pl

from ...... import rule
from ......facts import RouteFact
from ......query import CountQuery
from ......table import Table
from ..relations import RouteTables, count_query


@rule("ALL-ROUT0003")
def inconsistent_route_path_style(subject: Table[RouteFact]) -> CountQuery:
    """Count route segments spelled against the convention the rest of the paths follow.

    Definition
    ----------
    Read every path segment this repository declares, decide which word separator the majority use,
    and report a segment that uses the other one. A URL is an interface a caller types, and one
    that answers at `/user-profiles` but not at `/user_profiles` fails in a way that looks like an
    outage rather than a typo. The convention itself does not matter, and holding one does.

    Evidence
    --------
    Each finding names the path, the segment, and the separator the repository otherwise uses. The
    value is the number of segments spelled against it.

    Exceptions
    ----------
    A parameter segment is skipped, because it names a variable rather than a word a caller types.
    A repository with no separated segment at all has no convention to break and returns nothing.
    A path that has to match an external specification keeps that specification's spelling, which
    is a reason to exclude the module rather than to change the path.

    Examples
    --------
    Where `/user-profiles` and `/order-items` are declared, a `/audit_log` returns `1`. Where every
    path is one word, nothing is reported, because nothing has been decided yet.

    References
    ----------
    Cites "Google API Design Guide", resource naming
    https://cloud.google.com/apis/design/resource_names
    Cites "Microsoft REST API Guidelines", URL structure
    https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md
    Cites "Architectural Styles and the Design of Network-based Software Architectures"
    """
    relations = RouteTables(subject)
    routes = relations.routes()
    segments = (
        routes.select("fact_id", "record_id", pl.col("route_path").str.split("/").alias("segment"))
        .explode("segment", empty_as_null=True)
        .filter((pl.col("segment") != "") & ~pl.col("segment").str.contains("{", literal=True))
        .with_columns(
            pl.col("segment").str.contains("-", literal=True).alias("hyphenated"),
            pl.col("segment").str.contains("_", literal=True).alias("underscored"),
        )
    )
    conventions = (
        segments.group_by("fact_id", maintain_order=True)
        .agg(
            pl.col("hyphenated").sum().cast(pl.UInt64).alias("hyphenated"),
            pl.col("underscored").sum().cast(pl.UInt64).alias("underscored"),
        )
        .with_columns(
            pl.when(pl.col("hyphenated") > pl.col("underscored"))
            .then(pl.lit("-"))
            .otherwise(pl.lit("_"))
            .alias("expected"),
            pl.when(pl.col("hyphenated") > pl.col("underscored"))
            .then(pl.lit("_"))
            .otherwise(pl.lit("-"))
            .alias("unexpected"),
        )
        .filter(
            (pl.col("hyphenated") > 0)
            & (pl.col("underscored") > 0)
            & (pl.col("hyphenated") != pl.col("underscored"))
        )
    )
    contributions = (
        segments.join(conventions, on="fact_id", how="inner")
        .filter(pl.col("segment").str.contains(pl.col("unexpected"), literal=True))
        .group_by("fact_id", "record_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("amount"),
            pl.col("expected").first(),
            pl.col("unexpected").first(),
        )
    )
    selected = (
        routes.join(contributions, on=["fact_id", "record_id"], how="inner")
        .sort("fact_order", "ordinal")
        .with_columns(
            pl.int_range(pl.len()).over("fact_id").cast(pl.UInt64).alias("finding_order")
        )
    )
    message = pl.concat_str(
        pl.lit("`"),
        pl.col("route_path"),
        pl.lit("` uses `"),
        pl.col("unexpected"),
        pl.lit("` in "),
        pl.col("amount"),
        pl.lit(" segments while the repository route convention uses `"),
        pl.col("expected"),
        pl.lit("`"),
    )
    return count_query(relations, selected, message, "inconsistent route path style")
