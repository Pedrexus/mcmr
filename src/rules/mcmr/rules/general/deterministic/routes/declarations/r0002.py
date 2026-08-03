import polars as pl

from ...... import rule
from ......facts import RouteFact
from ......query import CountQuery
from ......table import Table
from ..relations import RouteTables, count_query


@rule("ALL-ROUT0002")
def unreached_declared_route(subject: Table[RouteFact]) -> CountQuery:
    """Count routes no client in this repository names, where other routes are named.

    Definition
    ----------
    Report a declared route whose path no other file states as a literal, but only in a repository
    where some declared route is named that way. A route nobody calls is either a surface someone
    forgot to remove or a contract someone forgot to wire, and both cost the reader the same
    afternoon deciding which one it is. The guard matters more than the rule, because a repository
    holding only a server has its clients elsewhere, and every route in it would read as unreached.

    Evidence
    --------
    Each finding names the method, the path, and where it is declared. The value is the number of
    unreached routes.

    Exceptions
    ----------
    A route a mounted router composes a prefix onto is skipped, since the path a client states is
    not the path the declaration states. A parameterized route is skipped for the same reason,
    because `/users/{id}` and `/users/7` are different strings and no literal match can prove they
    are the same route. A public API is legitimately unreached from inside its own repository, and
    a project that publishes one turns this rule off rather than deleting its surface.

    Examples
    --------
    In a repository whose frontend calls `"/api/users"` and `"/api/orders"`, a declared
    `"/api/legacy"` that nothing names returns `1`. In a repository with no client at all, every
    route returns `0`, because there is nothing to conclude from silence.

    References
    ----------
    Cites "Vulture documentation", dead code detection and its stated confidence limits
    https://github.com/jendrikseipp/vulture
    Cites "Refactoring", remove dead code
    Cites "OpenAPI Specification", paths and operations
    https://spec.openapis.org/oas/latest.html#paths-object
    """
    relations = RouteTables(subject)
    judged = relations.routes().filter(
        ~pl.col("is_prefix_composed") & ~pl.col("route_path").str.contains("{", literal=True)
    )
    referenced = judged.group_by("fact_id", maintain_order=True).agg(
        (pl.col("references.length") > 0).any().alias("has_reference")
    )
    selected = (
        judged.join(referenced, on="fact_id", how="left")
        .filter(pl.col("has_reference") & (pl.col("references.length") == 0))
        .sort("fact_order", "ordinal")
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
        pl.lit("` is declared here but no retained client reference names its path"),
    )
    return count_query(relations, selected, message, "unreached declared route")
