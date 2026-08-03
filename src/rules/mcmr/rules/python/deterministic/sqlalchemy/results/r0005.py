import polars as pl

from ...... import rule
from ......facts import QueryFact
from ......query import CountQuery
from ......table import Table
from ..relations import QueryTables, count_query


@rule("PY-SQLA0005")
def sqlmodel_primary_key_get(subject: Table[QueryFact]) -> CountQuery:
    """Prefer `Session.get` for provable SQLModel primary-key lookups.

    Definition
    ----------
    Report the exact chain `session.exec(select(Item).where(Item.id == key)).first()` when the same
    module declares `Item` as a SQLModel table and marks `id` as a primary key. The rule requires a
    resolved SQLModel session, one selected model, one equality predicate, and no execution
    options.

    Evidence
    --------
    Each finding points to one complete primary-key lookup chain. The value is the number of exact
    chains.

    Exceptions
    ----------
    Composite keys, imported models, aliases, statement variables, additional predicates, eager
    loading options, and non-`first` result contracts remain unreported. They can change query
    semantics and need explicit review.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       hero = session.exec(select(Hero).where(Hero.id == hero_id)).first()

    Good
    ~~~~
    .. code-block:: python

       hero = session.get(Hero, hero_id)

    References
    ----------
    Cites "SQLModel documentation", primary-key lookup guidance
    https://sqlmodel.tiangolo.com/tutorial/one/#select-by-id-with-get
    Cites "SQLAlchemy documentation", Session.get identity-map contract
    https://docs.sqlalchemy.org/en/21/orm/session_api.html#sqlalchemy.orm.Session.get
    """
    relations = QueryTables(subject)
    selected = relations.operations().filter(
        (pl.col("kind") == "primary_key_first")
        & (pl.col("framework") == "sqlmodel")
        & (pl.col("selected_expression_count") == 1)
        & pl.col("has_primary_key_equality")
        & ~pl.col("has_execution_options")
    )
    return count_query(
        relations,
        selected,
        message="Primary-key selection can use the session identity-map-aware `get` API",
        measurement="sqlmodel primary key get",
    )
