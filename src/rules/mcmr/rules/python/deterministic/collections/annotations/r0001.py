import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ParameterFact
from ......query import FindingQuery, OccurrenceQuery, RuleQuery
from ......table import Table


@rule("PY-COLL0001")
def concrete_collection_parameter(subject: Table[ParameterFact]) -> OccurrenceQuery:
    """Detect concrete collection parameters that require only an abstract capability.

    Definition
    ----------
    Inspect operations performed directly on parameters annotated as `list`, variadic
    `tuple`, `dict`, or `set`. Report a broader `collections.abc` input contract only when
    all observed uses are known and non-mutating. A write through a subscript, which is
    `values[key] = held` or `del values[key]`, reaches the same mutating method a named call
    reaches and keeps the concrete contract. This applies the Python convention of
    accepting the narrowest required capability while leaving concrete return types alone.

    Evidence
    --------
    Each finding names the callable, the parameter, the concrete annotation it declares, and the
    exact place the source states it, beside how many operations the body performs on it, which
    is what proves nothing needs the concrete type. An unknown call, mutation, fixed-position
    tuple, or mixed capability set suppresses the finding instead of guessing. The repair is a
    choice between the protocols the body could have asked for.

    Exceptions
    ----------
    Keep concrete types at serialization, C-extension, framework, dispatch, hashing, and other
    exact representation boundaries. Fixed heterogeneous tuples may be records, coordinates,
    protocol fields, or hash keys. Mutable parameters should retain a mutable contract.

    Examples
    --------
    `def first(values: list[int]): return values[0]` returns `true` and can accept `Sequence[int]`,
    and so does `def save(row: dict[str, str]): return row.get("id")`, which can accept
    `Mapping[str, str]`. `def add(values: list[int]): values.append(1)` returns `false`, because
    appending needs a mutable contract, and so does
    `def store(row: dict[str, str]): row["id"] = "1"`, because writing one entry needs the same
    contract. A parameter whose uses the provider could not all resolve also returns `false`.

    References
    ----------
    Cites "Fluent Python", chapter 13, Interfaces, Protocols, and ABCs
    Cites "The Python Standard Library", `typing`, generic `Sequence` and `Mapping` parameters
    Cites "The Python Standard Library", `collections.abc` abstract methods and mixins
    """
    concrete = ["list", "tuple", "dict", "set"]
    mutating = [
        "add",
        "append",
        "clear",
        "delitem",
        "extend",
        "insert",
        "pop",
        "remove",
        "setitem",
        "update",
    ]
    relations = subject
    facts = relations.facts()
    mutation_counts = (
        relations.values("parameters.operations")
        .filter(pl.col("string_value").is_in(mutating))
        .group_by("parent_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("mutation_count"))
    )
    selected = (
        relations.records("parameters")
        .join(mutation_counts, left_on="record_id", right_on="parent_id", how="left")
        .with_columns(pl.col("mutation_count").fill_null(0))
        .filter(
            pl.col("annotation").is_in(concrete)
            & pl.col("all_uses_known")
            & ~pl.col("is_return_value")
            & (pl.col("mutation_count") == 0)
        )
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("selected_count")
    )
    frame = (
        facts.join(counts, on="fact_id", how="left")
        .with_columns(pl.col("selected_count").fill_null(0))
        .with_columns((pl.col("selected_count") > 0).alias("value"))
    )
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
    return RuleQuery.boolean(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("owner"),
                pl.lit("` declares `"),
                pl.col("name"),
                pl.lit("` as a `"),
                pl.col("annotation"),
                pl.lit("` and never does anything only a `"),
                pl.col("annotation"),
                pl.lit("` can do"),
            ),
            (
                ("operations on it", pl.col("operations.length"), Unit.COUNT),
                ("of them needing the concrete type", pl.col("mutation_count"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("ask `"),
                pl.col("name"),
                pl.lit("` for the capability the body uses"),
            ),
            options=("an iterable it walks", "a mapping or a set it only looks into"),
            evidence=pl.col("evidence"),
        ),
    )
