import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import PydanticModelFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import PydanticModelTables


@rule("PY-PYDA0007")
def variadic_tuple_model_field(subject: Table[PydanticModelFact]) -> CountQuery:
    """Find Pydantic fields that require a homogeneous tuple representation.

    Definition
    ----------
    Inspect directly declared fields on Pydantic and recognized house model bases. Report a field
    when its annotation contains an arbitrary-length homogeneous `tuple[T, ...]`, including the
    deprecated `typing.Tuple` spelling and imported aliases. A model boundary should normally
    state the operations or normalized representation it needs rather than require callers to
    supply one immutable concrete collection.

    Evidence
    --------
    Each finding names the model, field, exact annotation, and annotation range. The value is the
    number of variadic tuple fields. Fixed heterogeneous tuples such as `tuple[int, int]` remain
    untouched because their positions form a record rather than a general collection.

    Exceptions
    ----------
    Keep a variadic tuple when tuple identity is itself part of the domain or public serialized
    contract. Prefer `Sequence[T]` when the model should preserve list or tuple input, and
    `list[T]` when validation should normalize input to one mutable representation. `Container[T]`
    expresses membership-only APIs but Pydantic needs an explicit schema adapter or arbitrary-type
    policy for it, so it is not an automatic model-field replacement.

    Examples
    --------
    Bad
    ~~~
    `class Job(FrozenModel): tags: tuple[str, ...] = ()` fixes a concrete representation without
    proving that tuple identity matters.

    Good
    ~~~~
    `tags: Sequence[str] = ()` preserves accepted sequence inputs. `tags: list[str] = []` states
    that the validated model owns a normalized list. `point: tuple[int, int]` remains a fixed-shape
    record and is not reported.

    References
    ----------
    Cites "Pydantic documentation", tuple and sequence validation
    https://pydantic.dev/docs/validation/latest/api/pydantic/standard_library_types/
    Cites "The Python Standard Library", sequence abstract base classes
    https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence
    Cites "Python typing specification", tuple types
    https://typing.python.org/en/latest/spec/tuples.html
    """
    tables = PydanticModelTables(subject)
    selected = (
        tables.fields()
        .filter(pl.col("owner_is_pydantic_model") & pl.col("contains_variadic_tuple"))
        .sort("fact_order", "model_order", "ordinal")
        .with_columns(
            pl.int_range(pl.len()).over("fact_id").alias("finding_order"),
            pl.col("span.path").alias("path"),
            pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
        )
        .join(tables.facts().select("fact_id", "evidence"), on="fact_id", how="left")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = (
        tables.facts()
        .join(counts, on="fact_id", how="left")
        .with_columns(pl.col("value").fill_null(0))
    )
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("model_name"),
            pl.lit("."),
            pl.col("name"),
            pl.lit("` uses `"),
            pl.col("annotation"),
            pl.lit("`, which fixes a homogeneous collection to tuple identity"),
        ),
        (("variadic tuple model field", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
