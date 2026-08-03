import polars as pl

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import AttributeAccessFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import Table


@rule("PY-ENUM0005", fix_safety=FixSafety.SAFE)
def prefer_enum_conversion(subject: Table[AttributeAccessFact]) -> CountQuery:
    """Prefer public conversions over direct standard `StrEnum` and `IntEnum` values.

    Definition
    ----------
    Report `.value` reads only when local syntax proves that the receiver is a standard-behavior
    `StrEnum` or `IntEnum`. Proof may come from a direct local member, a member lookup, a local
    enum constructor, an unshadowed concrete annotation, or iteration over a known local enum
    class. Recognize direct and aliased imports from the standard `enum` module. Use `str(member)`
    for a `StrEnum` and `int(member)` for an `IntEnum`. Each proven expression receives a safe
    UTF-8 byte edit that replaces the complete access. The value is the number of accesses found.

    Evidence
    --------
    Each finding records the proven enum kind, conversion, source range, and complete replacement.
    Ordinary objects with a `value` attribute and enum types imported from application modules are
    not inferred from spelling. Concrete annotations must name a nonempty local enum class.

    Exceptions
    ----------
    Do not report plain `Enum`, broad base annotations, ambiguous or rebound names, local classes
    with unknown mixins, or classes that define the relevant `__str__` or `__int__` conversion.
    Direct `.value` access remains appropriate when code deliberately needs a representation that
    differs from the enum's public string or integer conversion.

    Examples
    --------
    Bad
    ~~~
    `Color.RED.value`, `status.value` when `status: Status`, and `[item.value for item in Status]`.

    Good
    ~~~~
    `str(Color.RED)`, `int(HttpCode.OK)`, and `record.value` for an ordinary model field.

    References
    ----------
    Cites "The Python Standard Library", `StrEnum`
    https://docs.python.org/3/library/enum.html#enum.StrEnum
    Cites "The Python Standard Library", `IntEnum`
    https://docs.python.org/3/library/enum.html#enum.IntEnum
    Cites "The Python Standard Library", enum
    https://docs.python.org/3/library/enum.html
    """
    relations = subject
    conversions = (
        relations.values("accesses.receiver_type_bases")
        .filter(pl.col("string_value").is_in(["StrEnum", "IntEnum"]))
        .group_by("parent_id", maintain_order=True)
        .agg(
            (pl.col("string_value") == "StrEnum").any().alias("has_string_conversion"),
            (pl.col("string_value") == "IntEnum").any().alias("has_integer_conversion"),
        )
    )
    selected = (
        relations.records("accesses")
        .join(conversions, left_on="record_id", right_on="parent_id", how="inner")
        .filter(
            (pl.col("name") == "value")
            & (pl.col("has_string_conversion") | pl.col("has_integer_conversion"))
        )
        .with_columns(
            pl.when(pl.col("has_string_conversion"))
            .then(pl.lit("str"))
            .otherwise(pl.lit("int"))
            .alias("conversion")
        )
    )
    frame = relations.counted(selected)
    finding_rows = selected.join(
        relations.facts().select("fact_id", "evidence"),
        on="fact_id",
        how="inner",
    ).with_columns(
        pl.col("node.span.path").alias("path"),
        pl.col("node.span.start_line").alias("start_line"),
        pl.col("node.span.start_column").alias("start_column"),
        pl.col("node.span.end_line").alias("end_line"),
        pl.col("node.span.end_column").alias("end_column"),
    )
    rewrites = selected.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.concat_str(
            pl.col("conversion"), pl.lit("("), pl.col("receiver_text"), pl.lit(")")
        ).alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = selected.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("node.id").alias("id"),
        pl.col("node.span.path").alias("path"),
        pl.col("node.span.start_line").alias("start_line"),
        pl.col("node.span.start_column").alias("start_column"),
        pl.col("node.span.end_line").alias("end_line"),
        pl.col("node.span.end_column").alias("end_column"),
        pl.col("node.kind").alias("kind"),
        pl.col("node.text").alias("text"),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("receiver_text"),
                pl.lit(".value` exposes an enum representation that public `"),
                pl.col("conversion"),
                pl.lit("` conversion already provides"),
            ),
            (("prefer enum conversion", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Convert each proven enum value read through the enum's own public conversion.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
