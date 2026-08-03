import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-MODE0004")
def manual_model_attribute_projection_count(
    subject: Table[ClassFact], *, minimum_attributes: NonNegativeInt = 4
) -> CountQuery:
    """Count structures that manually repeat fields from one model instance.

    Definition
    ----------
    Inspect dictionary literals, sequences of key and value pairs, and keyword calls. Group direct
    attribute reads by their root object when each output key matches the attribute name after
    hyphen normalization. Report a structure that repeats at least `minimum_attributes` distinct
    fields. This is evidence that a Pydantic model, dataclass, or similar typed value already owns
    the schema and should provide the projection.

    Evidence
    --------
    Each finding records the source range, root object, distinct projected attribute count, and
    every repeated attribute. The rule does not require static proof of the root type because the
    matching keys and configured count form the conservative structural signal. The value is the
    number of structures repeating enough fields of one model instance.

    Exceptions
    ----------
    Different output names, computed values involving several attributes, unpacking, positional
    constructor calls, and projections below the threshold are ignored. Explicit projection can
    remain when the target schema intentionally differs, excludes secrets, or requires a stable
    compatibility boundary. Prefer `model_dump` include or exclude controls, a typed conversion
    model, or one named serializer over a second handwritten field list.

    Examples
    --------
    Bad
    ~~~
    A tuple manually lists `("id", definition.id)`, `("summary", definition.summary)`, and many
    more matching fields before rendering them.

    Good
    ~~~~
    `definition.model_dump(mode="json", exclude_defaults=True)` reads the model-owned schema.
    A four-field API payload whose names and transformations deliberately differ remains explicit.

    References
    ----------
    Cites "Pydantic documentation", model serialization
    https://docs.pydantic.dev/latest/concepts/serialization/#modelmodel_dump
    Cites "The Python Standard Library", dataclasses `asdict`
    https://docs.python.org/3/library/dataclasses.html#dataclasses.asdict
    Cites "Refactoring", Data Class and Extract Class
    """
    facts = subject.lazy(ClassRelation.FACTS)
    attributes = (
        subject.lazy(ClassRelation.PROJECTION_ATTRIBUTES)
        .group_by("projection_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("attribute_names"))
    )
    outputs = (
        subject.lazy(ClassRelation.PROJECTION_OUTPUT_KEYS)
        .with_columns(pl.col("value").str.replace_all("-", "_").alias("normalized"))
        .group_by("projection_id", maintain_order=True)
        .agg(pl.col("normalized").sort_by("ordinal").alias("normalized_output_keys"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.PROJECTIONS)
        .join(attributes, on="projection_id", how="left")
        .join(outputs, on="projection_id", how="left")
        .with_columns(
            pl.col("attribute_names").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("normalized_output_keys").fill_null(pl.lit([], dtype=pl.List(pl.String))),
        )
        .filter(
            (pl.col("attribute_names").list.n_unique() >= minimum_attributes)
            & (
                pl.col("normalized_output_keys").list.unique().list.sort()
                == pl.col("attribute_names").list.unique().list.sort()
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
                pl.lit("projection from `"),
                pl.col("root"),
                pl.lit("` repeats model attributes `"),
                pl.col("attribute_names").list.join("`, `"),
                pl.lit("`"),
            ),
            (("manual model attribute projection count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
