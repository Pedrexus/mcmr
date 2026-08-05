import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-MODE0006")
def empty_declarative_model(subject: Table[ClassFact]) -> CountQuery:
    """Require every declarative model to own at least one field.

    Definition
    ----------
    Report a recognized Pydantic, house model, SQL table, or dataclass with no declared or
    inherited fields. A model without state is a namespace, marker, or behavior holder and should
    state that narrower role directly instead of paying for a data-model foundation.

    Evidence
    --------
    Each finding names the empty model and its exact source range. The value is the number of empty
    declarative models in the file.

    Exceptions
    ----------
    A foundation is not a model. A base that owns no fields and either states the `model_config`
    every class below it inherits or is already derived by classes that do own fields exists to fix
    validation policy, so it is read as the foundation rather than as an empty model, wherever the
    project keeps it. Framework-required sentinel models can remain through an exact path
    exclusion. Protocols and abstract behavioral contracts are not concrete data models and are
    excluded.

    Examples
    --------
    `class Ready(FrozenModel): pass` is reported. `class Ready(FrozenModel): value: bool` and an
    explicit `Protocol` are accepted. A base whose whole body is `model_config` is also accepted,
    since it states what everything below it derives.

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "Refactoring", Data Class
    """
    facts = subject.lazy(ClassRelation.FACTS)
    classes = subject.lazy(ClassRelation.CLASSES)
    abstract_bases = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .filter(pl.col("value").str.split(".").list.last().is_in(["ABC", "Protocol", "ABCMeta"]))
        .select("class_id")
        .unique(maintain_order=True)
        .with_columns(pl.lit(True).alias("has_abstract_base"))
    )
    abstract_methods = (
        subject.lazy(ClassRelation.METHOD_DECORATORS)
        .filter(
            pl.col("value")
            .str.split(".")
            .list.last()
            .is_in(["abstractmethod", "abstractproperty"])
        )
        .join(
            subject.lazy(ClassRelation.METHODS).select("method_id", "class_id"),
            on="method_id",
            how="inner",
        )
        .select("class_id")
        .unique(maintain_order=True)
        .with_columns(pl.lit(True).alias("has_abstract_method"))
    )
    selected = (
        classes.join(abstract_bases, on="class_id", how="left")
        .join(abstract_methods, on="class_id", how="left")
        .with_columns(
            pl.col("has_abstract_base").fill_null(False),
            pl.col("has_abstract_method").fill_null(False),
        )
        .filter(
            pl.col("is_declarative_model")
            & (pl.col("field_count") == 0)
            & ~pl.col("has_inherited_fields")
            & ~pl.col("is_protocol")
            & ~pl.col("has_abstract_base")
            & ~pl.col("has_abstract_method")
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
            pl.concat_str(pl.lit("`"), pl.col("name"), pl.lit("` is a model with no fields")),
            (("empty declarative model", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
        ),
    )
