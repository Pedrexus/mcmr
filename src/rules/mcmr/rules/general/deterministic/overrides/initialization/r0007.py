import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query


@rule("ALL-OVER0007")
def initializer_called_on_a_stranger(subject: Table[OverrideFact]) -> CountQuery:
    """Count initializers a subclass runs on a class it does not actually inherit from.

    Definition
    ----------
    Read what the subclass initializer calls, and report a call to the initializer of a class the
    subclass never names as a base. Running someone else's constructor on your own instance is
    borrowing setup by hand. It works right up to the day that class changes what it sets, and
    then a type the reader never connected to this one starts failing, because the only thing
    binding them together was a line nobody documented.

    It is usually a copy of the right line with the wrong name in it, which is exactly the kind
    of mistake the inheritance chain can prove and a reader cannot.

    Evidence
    --------
    Each finding names the subclass, the stranger whose initializer it ran, and the bases the
    subclass actually declares. The value is the number of stranger initializers called.

    Exceptions
    ----------
    A call reaching `super` is never a stranger, since Python picks the class it lands on. A call
    naming any declared base is what this rule exists to allow. The judgment is made once per
    subclass, on the link to the base a reader meets first, so a class with two bases counts one
    stray call once rather than once per base.

    A class assigned to a local name before its initializer is called is invisible, because the
    graph resolves the receiver as written. A deliberate mixin composed by hand rather than by
    inheritance is a legitimate design that this rule reports, and a project built that way turns
    it off.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Report(Document):
           def __init__(self):
               Spreadsheet.__init__(self)

    Good
    ~~~~
    .. code-block:: python

       class Report(Document, Spreadsheet):
           def __init__(self):
               super().__init__()

    References
    ----------
    Generalizes Pylint W0233 non-parent-init-called
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/non-parent-init-called.html
    Cites "Python's super() Considered Super", PyCon 2015
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    Cites "Design Patterns", prefer composition over inheritance
    """
    relations = OverrideTables(subject)
    base_names = relations.values("base_names").select(
        "fact_id",
        "ordinal",
        pl.col("string_value").alias("base_name"),
    )
    first = base_names.filter(pl.col("ordinal") == 0).select(
        "fact_id",
        pl.col("base_name").alias("first_base"),
    )
    calls = relations.values("initializer_calls").select(
        "fact_id",
        "value_id",
        pl.col("string_value").alias("called_initializer"),
    )
    known = calls.join(
        base_names,
        left_on=["fact_id", "called_initializer"],
        right_on=["fact_id", "base_name"],
        how="anti",
    )
    selected = (
        known.join(first, on="fact_id", how="left")
        .join(relations.facts().select("fact_id", "depth", "base"), on="fact_id")
        .filter(
            (pl.col("depth") == 1)
            & (pl.col("first_base").fill_null("") == pl.col("base").str.split(".").list.last())
            & (pl.col("called_initializer") != "super")
        )
    )
    return count_query(
        relations.counted(selected),
        "initializer called on a stranger",
    )
