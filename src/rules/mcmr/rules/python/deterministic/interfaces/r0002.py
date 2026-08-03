import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import ClassFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import ClassRelation, Table

_ABSTRACT_BASES = ["ABC", "ABCMeta"]
_ABSTRACT_DECORATORS = [
    "abstractclassmethod",
    "abstractmethod",
    "abstractproperty",
    "abstractstaticmethod",
]


@rule("PY-INTE0002")
def single_implementation_abstract_base(subject: Table[ClassFact]) -> CountQuery:
    """Count abstract bases that support only one repository implementation.

    Definition
    ----------
    Build the repository inheritance graph and report a top-level Python class that explicitly
    derives from `ABC` or `ABCMeta`, or declares an abstract member, when exactly one descendant
    implements it. An abstract base adds indirection to let implementations vary. With only one
    implementation, the indirection has cost but no choice.

    Evidence
    --------
    Each finding names the abstract base, its one descendant, and the complete declaration range.
    The value is the number of single-implementation abstract bases in the file.

    Exceptions
    ----------
    Protocols are excluded because structural implementations need not inherit the protocol and a
    closed-world subclass graph cannot count them. An abstract base with two or more descendants
    has earned its variation point. A base with no descendants is owned by the separate unused
    declaration and abstraction reach rules.

    Examples
    --------
    Bad
    ~~~
    An abstract `FactProvider` with only `DependencyProvider` below it returns `1`.

    Good
    ~~~~
    An abstract `Renderer` implemented by `JsonRenderer` and `TextRenderer` returns `0`.

    References
    ----------
    Cites "The Python Standard Library", `abc`
    Cites "A Philosophy of Software Design", deep modules and useful abstractions
    """
    facts = subject.lazy(ClassRelation.FACTS)
    classes = subject.lazy(ClassRelation.CLASSES)
    base_contracts = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .filter(pl.col("value").str.split(".").list.last().is_in(_ABSTRACT_BASES))
        .select("class_id")
    )
    method_contracts = (
        subject.lazy(ClassRelation.METHOD_DECORATORS)
        .filter(pl.col("value").str.split(".").list.last().is_in(_ABSTRACT_DECORATORS))
        .join(
            subject.lazy(ClassRelation.METHODS).select("method_id", "class_id"),
            on="method_id",
            how="inner",
        )
        .select("class_id")
    )
    contracts = pl.concat([base_contracts, method_contracts]).unique(maintain_order=True)
    descendants = (
        subject.lazy(ClassRelation.DIRECT_SUBCLASSES)
        .group_by("class_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("direct_subclasses"))
    )
    selected = (
        classes.join(contracts, on="class_id", how="inner")
        .join(descendants, on="class_id", how="left")
        .with_columns(pl.col("direct_subclasses").fill_null(pl.lit([], dtype=pl.List(pl.String))))
        .filter(
            (pl.col("scope") == "module")
            & ~pl.col("is_protocol")
            & (pl.col("descendant_count") == 1)
        )
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
                pl.lit("` is an abstract base with only `"),
                pl.col("direct_subclasses").list.first(),
                pl.lit("` below it"),
            ),
            (("single implementation abstract base", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
        ),
    )
