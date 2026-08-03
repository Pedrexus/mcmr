import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-MODE0005")
def standard_dataclass_model(subject: Table[ClassFact]) -> CountQuery:
    """Replace state-bearing standard dataclasses with the approved model foundation.

    Definition
    ----------
    Report a Python class decorated with the standard `dataclass` decorator when it declares at
    least one field and no ordinary behavior. Such a class is already a data model, so the project
    foundation should own validation, serialization, immutability, and schema policy consistently.

    Evidence
    --------
    Each finding names the dataclass and its field count. The value is the number of declarative
    dataclasses in the file.

    Exceptions
    ----------
    A class whose identity is a language interop record or whose methods implement ordinary
    behavior can remain a dataclass through a path exclusion. Empty marker classes are handled by
    the separate nonempty-model rule.

    Examples
    --------
    `@dataclass class Point` with `x` and `y` fields is reported. `class Point(FrozenModel)` is the
    accepted project model shape.

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "The Python Standard Library", dataclasses
    https://docs.python.org/3/library/dataclasses.html
    """
    facts = subject.lazy(ClassRelation.FACTS)
    selected = subject.lazy(ClassRelation.CLASSES).filter(
        pl.col("is_dataclass") & (pl.col("field_count") > 0) & ~pl.col("has_ordinary_behavior")
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
                pl.lit("` is a standard dataclass with "),
                pl.col("field_count"),
                pl.lit(" fields instead of an approved Pydantic model"),
            ),
            (("standard dataclass model", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
        ),
    )
