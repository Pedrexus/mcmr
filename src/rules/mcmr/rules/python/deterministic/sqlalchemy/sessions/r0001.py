import polars as pl

from ...... import rule
from ......facts import QueryFact
from ......query import CountQuery
from ......table import Table
from ..relations import QueryTables, count_query


@rule("PY-SQLA0001")
def async_session_expiration_policy(subject: Table[QueryFact]) -> CountQuery:
    """Require explicit non-expiring SQLAlchemy async session factories.

    Definition
    ----------
    Find calls statically resolved to SQLAlchemy `async_sessionmaker`. Report a factory unless it
    sets `expire_on_commit=False`. SQLAlchemy recommends this async setting so ordinary attribute
    access after commit does not attempt implicit database I/O. A factory expanded through
    unknown keyword arguments is left unreported because its effective policy cannot be proven.

    Evidence
    --------
    Each finding points to one factory call whose commit expiration remains enabled or unknown.
    The value is the number of actionable factories.

    Exceptions
    ----------
    Keep expiration only when the application deliberately refreshes or awaits every subsequent
    access and has tests proving that lifecycle. Direct `AsyncSession` construction and custom
    factory wrappers are not inferred by this narrow rule.

    Examples
    --------
    Bad
    ~~~
    `sessions = async_sessionmaker(engine)` retains the default commit expiration and is
    reported.

    Good
    ~~~~
    `sessions = async_sessionmaker(engine, expire_on_commit=False)` keeps post-commit attributes
    available without hidden I/O.

    References
    ----------
    Cites "SQLAlchemy documentation", asyncio documentation, preventing implicit I/O
    https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession
    Cites "SQLAlchemy documentation", async session factory API
    https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.async_sessionmaker
    """
    relations = QueryTables(subject)
    selected = relations.operations().filter(
        (pl.col("kind") == "async_sessionmaker")
        & pl.col("expire_on_commit")
        & ~pl.col("has_unknown_keywords")
    )
    return count_query(
        relations,
        selected,
        message=(
            "`async_sessionmaker` retains commit expiration and can trigger implicit I/O "
            "after commit"
        ),
        measurement="async session expiration policy",
    )
