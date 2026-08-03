import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query


@rule("ALL-OVER0006")
def subclass_initializer_skips_its_base(subject: Table[OverrideFact]) -> CountQuery:
    """Count subclasses that write their own initializer and never run the one above them.

    Definition
    ----------
    Report a direct base that declares an initializer where the subclass declares one too and
    reaches neither `super` nor that base from inside it. Half a constructor ran, so the object
    exists and every attribute the base was going to set is simply missing. The first read of one
    raises an attribute error somewhere unrelated, and the reader who lands there has no reason to
    suspect a constructor, which is why this costs an afternoon rather than a minute.

    Finding the skipped initializer means resolving the base across the repository and then
    reading what the subclass initializer actually calls. Both halves live in the graph, and
    neither is visible from the subclass alone.

    Evidence
    --------
    Each finding names the subclass, the base whose initializer never ran, and the receivers the
    subclass initializer did call. The value is one for each base left unrun.

    Exceptions
    ----------
    Only a direct base is judged, because an initializer that calls `super` hands the rest of the
    chain to Python and a class further up is not the subclass's to call. A base whose initializer
    is marked abstract has nothing to run. A subclass with no initializer of its own inherits the
    base one intact and is not judged at all.

    A base that runs its setup somewhere other than an initializer is a design MCMR cannot see,
    and a project built that way turns this rule off rather than adding empty calls. Pylint also
    skips an initializer marked as a typing overload and a base that is a protocol, and neither
    exemption is read here.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Connection:
           def __init__(self):
               self.socket = open_socket()


       class PooledConnection(Connection):
           def __init__(self):
               self.pool = []

    Good
    ~~~~
    .. code-block:: python

       class PooledConnection(Connection):
           def __init__(self):
               super().__init__()
               self.pool = []

    References
    ----------
    Generalizes Pylint W0231 super-init-not-called
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/super-init-not-called.html
    Cites "Python's super() Considered Super", PyCon 2015
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    Cites "The Python Language Reference", the method resolution order
    """
    relations = OverrideTables(subject)
    declared = (
        relations.members("declared")
        .filter(pl.col("name") == "__init__")
        .select("fact_id")
        .unique()
    )
    inherited = relations.members("inherited").filter(
        (pl.col("name") == "__init__") & ~pl.col("is_promised")
    )
    calls = relations.values("initializer_calls").select(
        "fact_id",
        pl.col("string_value").alias("called_initializer"),
    )
    selected = (
        inherited.join(declared, on="fact_id", how="semi")
        .join(relations.facts().select("fact_id", "depth", "base"), on="fact_id")
        .join(calls, on="fact_id", how="left")
        .group_by("fact_id", maintain_order=True)
        .agg(
            pl.first("depth").alias("depth"),
            pl.first("base").alias("base"),
            pl.col("called_initializer").drop_nulls().alias("called_initializers"),
        )
        .filter(
            (pl.col("depth") == 1)
            & ~pl.col("called_initializers").list.contains("super")
            & ~pl.col("called_initializers").list.contains(
                pl.col("base").str.split(".").list.last()
            )
        )
    )
    return count_query(
        relations.counted(selected),
        "subclass initializer skips its base",
    )
