import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table


@rule("PY-CLAS0010")
def dynamic_super_receiver(subject: Table[SyntaxFact]) -> RuleQuery[int]:
    """Count `super` calls whose first argument is computed from the receiver.

    Definition
    ----------
    Report a method that calls a member on `super(type(self), self)` or on `super(self.__class__,
    self)`. Both spellings look like a way to avoid repeating the class name and both recurse
    forever the moment somebody subclasses the type, because the first argument is resolved at run
    time to the object's actual class, so the lookup restarts one step below where it started and
    reaches the same method again. The value is the number of such calls.

    Writing `super()` states the enclosing class at compile time and cannot make that mistake,
    which is why it is the only spelling worth having in a body that has one.

    Evidence
    --------
    The finding names the method and counts the calls inside it. A `super` object merely assigned
    to a name is not counted, since the defect is the lookup rather than the construction. The
    value is the number of `super` calls whose first argument is computed from the receiver.

    Exceptions
    ----------
    A first argument stating a class outright is left alone, even when it names an ancestor rather
    than the enclosing class, because skipping a step through the resolution order on purpose is a
    legal thing to do and telling it from an unrelated class needs the ancestors of the class
    beside the source of its methods, which no single fact carries.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Engine(Base):
           def run(self):
               return super(type(self), self).run()

    Good
    ~~~~
    .. code-block:: python

       class Engine(Base):
           def run(self):
               return super().run()

    References
    ----------
    Generalizes Pylint E1003 bad-super-call
    https://pylint.readthedocs.io/en/latest/user_guide/messages/error/bad-super-call.html
    Cites "The Python Standard Library", `super` and the zero-argument form
    https://docs.python.org/3/library/functions.html#super
    Cites "Python's super() Considered Super"
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = subject.lazy(SyntaxRelation.NODES)
    children = subject.lazy(SyntaxRelation.CHILDREN)
    members = nodes.filter(pl.col("kind") == "member").select(
        "fact_id", pl.col("ordinal").alias("parent_ordinal")
    )
    call_nodes = nodes.filter((pl.col("kind") == "call") & (pl.col("name") == "super"))
    calls = (
        children.join(members, on=["fact_id", "parent_ordinal"], how="inner")
        .join(
            call_nodes.select(
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .select(
            "fact_id",
            pl.col("child_ordinal").alias("parent_ordinal"),
            pl.col("child_ordinal").alias("call_ordinal"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
        )
    )
    dynamic = (
        children.filter(pl.col("child_order") == 1)
        .join(calls, on=["fact_id", "parent_ordinal"], how="inner")
        .join(
            nodes.filter(pl.col("name").is_in(["type", "__class__"])).select(
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                pl.col("name").alias("receiver"),
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .join(
            facts.filter(
                (pl.col("kind") == "callable") & pl.col("qualname").str.contains(".", literal=True)
            ).select("fact_id", "qualname"),
            on="fact_id",
            how="inner",
        )
    )
    counts = dynamic.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.when(
            (pl.col("kind") == "callable") & pl.col("qualname").str.contains(".", literal=True)
        )
        .then(pl.col("value").fill_null(0))
        .otherwise(0)
        .alias("value")
    )
    findings = FindingQuery.build(
        dynamic,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualname"),
            pl.lit("` computes the first `super` argument from `"),
            pl.col("receiver"),
            pl.lit("`"),
        ),
        (("dynamic super receiver", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("call_ordinal"),
    )
    return RuleQuery.integer(values, pl.col("value"), findings=findings)
