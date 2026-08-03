import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0007")
def hazardous_multiple_inheritance_mro_count(
    subject: Table[ClassFact],
) -> CountQuery:
    """Count deterministic MRO hazards among project-owned direct bases.

    Definition
    ----------
    Build the project inheritance graph and inspect undecorated classes with at least two resolved
    project-owned direct bases. Report a class when one direct base already inherits another, or
    when several direct bases provide the same concrete method and at least one implementation
    does not delegate that same method through zero-argument `super()`. Abstract methods,
    overloads, ellipsis or `pass` stubs, and `NotImplementedError` placeholders do not create a
    collision. Disjoint or fully cooperative mixins remain accepted.

    Evidence
    --------
    Each finding records base order, concrete colliding method owners, redundant ancestor edges,
    and the complete subclass range. Measurements expose the number of project bases, collisions,
    and precedence edges separately. The value is the number of classes carrying a proven
    order-sensitive hierarchy.

    Exceptions
    ----------
    External bases are not guessed. Decorated classes and classes with metaclass or other keywords
    are excluded because frameworks can define their own linearization contract. A collision is
    accepted when every direct implementation explicitly participates in cooperative dispatch.
    Composition may still be preferable, but this rule reports only proven order sensitivity.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class JsonLoader:
           def load(self) -> bytes:
               return b"json"

       class CachedLoader:
           def load(self) -> bytes:
               return b"cache"

       class Service(JsonLoader, CachedLoader):
           pass

       class Specialized(Base, BaseContract):
           pass

    Good
    ~~~~
    .. code-block:: python

       class TimestampMixin:
           def timestamp(self) -> float:
               return time.time()

       class NamedMixin:
           def name(self) -> str:
               return type(self).__name__

       class Record(TimestampMixin, NamedMixin):
           pass

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Cites "Python HOWTOs", method resolution order
    https://docs.python.org/3/howto/mro.html
    Cites "The Python Standard Library", zero-argument super
    https://docs.python.org/3/library/functions.html#super
    Cites "Python's super() Considered Super"
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    """
    facts = subject.lazy(ClassRelation.FACTS)
    direct_bases = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .group_by("class_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("direct_bases"))
    )
    decorator_counts = (
        subject.lazy(ClassRelation.CLASS_DECORATORS)
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .join(direct_bases, on="class_id", how="left")
        .join(decorator_counts, on="class_id", how="left")
        .with_columns(
            pl.col("direct_bases").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("decorator_count").fill_null(0),
        )
        .filter(
            (pl.col("direct_bases").list.len() >= 2)
            & (pl.col("decorator_count") == 0)
            & (
                pl.col("has_redundant_direct_base")
                | pl.col("has_noncooperative_concrete_collision")
            )
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` combines `"),
                pl.col("direct_bases").list.join("`, `"),
                pl.lit("` with a redundant base or a noncooperative concrete collision"),
            ),
            (("hazardous multiple inheritance mro count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
