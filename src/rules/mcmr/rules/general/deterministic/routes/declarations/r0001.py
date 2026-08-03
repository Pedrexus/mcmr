import polars as pl

from ...... import rule
from ......facts import RouteFact
from ......query import CountQuery
from ......table import Table
from ..relations import RouteTables, count_query


@rule("ALL-ROUT0001")
def duplicate_route_declaration(subject: Table[RouteFact]) -> CountQuery:
    """Count routes declared more than once for the same method and path.

    Definition
    ----------
    Report a method and path this repository declares in more than one place. Only one of them
    ever serves a request, and which one depends on registration order rather than on anything a
    reader can see. The other is dead code that looks live, so an edit to it changes nothing and
    the next reader spends the afternoon working out why.

    Evidence
    --------
    Each finding names the method, the path, and every file that declares it. The value is the
    number of methods and paths declared more than once.

    Exceptions
    ----------
    A route a mounted router composes a prefix onto is skipped, because its declared path is only
    part of the path it serves and two routers under different prefixes legitimately declare the
    same suffix. A framework that dispatches on more than method and path, such as one matching a
    content type or a host, can carry a real duplicate here.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       # users.py
       @app.get("/users")
       def list_users(): ...

       # admin.py
       @app.get("/users")
       def list_users_for_admin(): ...

    Good
    ~~~~
    .. code-block:: python

       @app.get("/users")
       def list_users(): ...

       @app.get("/admin/users")
       def list_users_for_admin(): ...

    References
    ----------
    Cites "Express documentation", the order routes are matched in
    https://expressjs.com/en/guide/routing.html
    Cites "FastAPI documentation", path operation order
    https://fastapi.tiangolo.com/tutorial/path-params/#order-matters
    Cites "Patterns of Enterprise Application Architecture", front controller
    """
    relations = RouteTables(subject)
    selected = (
        relations.routes()
        .filter(~pl.col("is_prefix_composed"))
        .group_by("fact_id", "method", "route_path", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("declaration_count"),
            pl.concat_str(pl.col("declared_in"), pl.lit(":"), pl.col("line"))
            .sort_by("ordinal")
            .alias("locations"),
            pl.col("declared_in").sort_by("ordinal").first().alias("finding_path"),
            pl.col("line").sort_by("ordinal").first().cast(pl.UInt64).alias("finding_start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("finding_start_column"),
            pl.col("line").sort_by("ordinal").first().cast(pl.UInt64).alias("finding_end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("finding_end_column"),
            pl.col("evidence").first(),
        )
    )
    selected = (
        selected.filter(pl.col("declaration_count") > 1)
        .sort("fact_id", "method", "route_path")
        .with_columns(
            pl.lit(1, dtype=pl.UInt64).alias("amount"),
            pl.int_range(pl.len()).over("fact_id").cast(pl.UInt64).alias("finding_order"),
        )
    )
    message = pl.concat_str(
        pl.lit("`"),
        pl.col("method"),
        pl.lit(" "),
        pl.col("route_path"),
        pl.lit("` is declared "),
        pl.col("declaration_count"),
        pl.lit(" times in `"),
        pl.col("locations").list.join("`, `"),
        pl.lit("`"),
    )
    return count_query(relations, selected, message, "duplicate route declaration")
