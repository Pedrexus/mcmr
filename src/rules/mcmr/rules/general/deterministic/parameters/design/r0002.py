from collections.abc import Sequence

import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ParameterFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-PARA0002")
def configuration_object_parameter(
    subject: Table[ParameterFact],
    *,
    minimum_reads: NonNegativeInt = 2,
    configuration_markers: Sequence[str] = ("config", "configuration", "options", "settings"),
) -> CountQuery:
    """Count parameters a callable only reads attributes from.

    Definition
    ----------
    Report a configuration parameter whose every resolved use is an attribute read, and which is
    read for at least `minimum_reads` distinct names. A configuration type is identified by the
    configurable, case-insensitive markers in its annotation. Such a parameter does not need the
    object, only those values. Taking the whole object hides which parts the callable depends on,
    forces every caller and every test to build a complete object, and couples the callable to a
    type it never uses as a type.

    Evidence
    --------
    Each finding names the callable, the parameter, its declared type, and every attribute name
    the body reads from it, since those names are the narrower contract the callable actually
    wants. The repair is a choice, because a settings object a framework hands over is not one a
    caller can unpack. The value is the number of such parameters.

    Exceptions
    ----------
    A value object such as a source span is not configuration and is skipped even when a renderer
    reads several of its fields. A parameter with any use other than an attribute read is skipped,
    because the callable then depends on the object itself. A parameter whose uses could not all
    be resolved is skipped rather than guessed. A project can replace `configuration_markers`,
    raise `minimum_reads`, or disable the rule where a framework deliberately supplies settings.

    Examples
    --------
    A function that reads only `config.host` and `config.port` returns `1` and should take those
    two values. A function reading `span.path` and `span.start_line` returns `0`, as does one that
    reads `config.host` and also passes `config` onward.

    References
    ----------
    Cites "Refactoring", replace parameter with explicit methods
    Cites "Clean Code", function arguments
    Cites "Implementation Patterns", on revealing intent in signatures
    """
    relations = subject
    facts = relations.facts()
    attributes = (
        relations.values("parameters.attribute_reads")
        .select("parent_id", "string_value")
        .unique(maintain_order=True)
        .group_by("parent_id", maintain_order=True)
        .agg(
            pl.col("string_value").sort().alias("attributes"),
            pl.len().cast(pl.UInt64).alias("attribute_count"),
        )
    )
    selected = (
        relations.records("parameters")
        .join(attributes, left_on="record_id", right_on="parent_id", how="inner")
        .filter(
            pl.col("all_uses_known")
            & (pl.col("operations.length") == 0)
            & (pl.col("attribute_count") >= minimum_reads)
            & pl.col("annotation").str.contains_any(
                configuration_markers,
                ascii_case_insensitive=True,
            )
        )
    )
    frame = relations.counted(selected)
    finding_rows = selected.join(
        facts.select(
            "fact_id",
            "evidence",
            pl.col("path").alias("fact_path"),
            pl.col("start_line").alias("fact_start_line"),
            pl.col("start_column").alias("fact_start_column"),
            pl.col("end_line").alias("fact_end_line"),
            pl.col("end_column").alias("fact_end_column"),
        ),
        on="fact_id",
        how="inner",
    ).with_columns(
        pl.coalesce("span.path", "fact_path").alias("path"),
        pl.coalesce("span.start_line", "fact_start_line").cast(pl.UInt64).alias("start_line"),
        pl.coalesce("span.start_column", "fact_start_column")
        .cast(pl.UInt64)
        .alias("start_column"),
        pl.coalesce("span.end_line", "fact_end_line").cast(pl.UInt64).alias("end_line"),
        pl.coalesce("span.end_column", "fact_end_column").cast(pl.UInt64).alias("end_column"),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("owner"),
                pl.lit("` takes `"),
                pl.col("name"),
                pl.lit("` as a whole `"),
                pl.col("annotation"),
                pl.lit("` and reads only `"),
                pl.col("attributes").list.join("`, `"),
                pl.lit("`"),
            ),
            (
                ("attributes read", pl.col("attribute_count"), Unit.COUNT),
                ("other operations on it", pl.col("operations.length"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("pass `"),
                pl.col("owner"),
                pl.lit("` the "),
                pl.col("attribute_count"),
                pl.when(pl.col("attribute_count") == 1)
                .then(pl.lit(" value"))
                .otherwise(pl.lit(" values")),
                pl.lit(" it reads"),
            ),
            options=(
                "take them as explicit parameters",
                "keep the object where a framework owns its shape",
            ),
            evidence=pl.col("evidence"),
        ),
    )
