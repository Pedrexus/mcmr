import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table


@rule("ALL-DEPE0003")
def repeated_external_unary_transformation(
    subject: Table[CallFact],
    *,
    minimum_repetitions: NonNegativeInt = 3,
    minimum_files: NonNegativeInt = 2,
    ignored_callables: tuple[str, ...] = (),
    first_party_modules: tuple[str, ...] = (),
    transformation_names: tuple[str, ...] = (
        "camelize",
        "canonicalize",
        "convert",
        "decode",
        "deserialize",
        "encode",
        "normalize",
        "parse",
        "sanitize",
        "serialize",
        "slugify",
        "underscore",
    ),
) -> CountQuery:
    """Find repeated unary transformations performed directly by external packages.

    Definition
    ----------
    Resolve absolute module and symbol imports to fully qualified third-party callables. Count
    calls whose final name identifies a configured transformation and that receive exactly one
    explicit positional argument with no keywords, then group identical callables across project
    files. Report a project-owned boundary candidate only after a group reaches both
    `minimum_repetitions` and `minimum_files`. Relative imports, standard-library imports,
    inferred or configured first-party modules, constructors, shadowed bindings, ambiguous
    aliases, decorator factories, starred arguments, and configured `ignored_callables` are
    excluded. `transformation_names` is the explicit semantic vocabulary that keeps ordinary API
    helpers out of this deterministic rule.

    Evidence
    --------
    Each finding records the external callable, occurrence and file counts, every matching source
    location, and a stable project-boundary candidate identifier. The result value counts the
    eligible calls in groups that reach both configured floors. One-offs remain observable in the
    provider fact without becoming failures that have no finding.

    Exceptions
    ----------
    A recognized operation and repetition still do not prove a useful domain abstraction. Ignore
    a callable when direct use is itself the project convention, extend `transformation_names`
    when the project uses another exact operation name, or raise the thresholds when a wrapper
    would only rename a stable dependency API. Configure additional first-party roots for
    nonstandard source layouts.
    `first_party_modules` names roots a nonstandard layout owns so its own code is not read as
    third party. Repository Git ignores decide which source files exist before this rule runs.

    Examples
    --------
    Bad
    ~~~
    Calling `inflection.underscore(value)` in three modules couples project naming policy to the
    external package at three sites.

    Good
    ~~~~
    Define one project function such as `python_name(value)` that calls
    `inflection.underscore(value)`, then depend on that named boundary. A single direct call or a
    call using keyword arguments does not trigger a finding.

    References
    ----------
    Cites "Refactoring", Extract Function
    https://refactoring.com/catalog/extractFunction.html
    Cites "Domain-Driven Design", Anti-Corruption Layer
    Cites "The Python Language Reference", the import system
    https://docs.python.org/3/reference/import.html
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    argument_counts = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter((pl.col("root_relation") == "argument") & (pl.col("depth") == 0))
        .group_by("call_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("argument_count"))
    )
    keyword_calls = subject.lazy(CallRelation.KEYWORDS).select("call_id").unique()
    first_party_match = (
        pl.any_horizontal(
            [
                (pl.col("qualified_name") == module)
                | pl.col("qualified_name").str.starts_with(f"{module}.")
                for module in first_party_modules
            ]
        )
        if first_party_modules
        else pl.lit(False)
    )
    eligible = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id", "fact_order"), on="fact_id", how="inner")
        .join(argument_counts, on="call_id", how="left")
        .with_columns(pl.col("argument_count").fill_null(0))
        .join(keyword_calls, on="call_id", how="anti")
        .filter(
            pl.col("is_external")
            & ~pl.col("is_standard_library")
            & ~pl.col("is_first_party")
            & ~pl.col("is_constructor")
            & ~pl.col("is_shadowed")
            & ~pl.col("has_ambiguous_alias")
            & ~pl.col("is_decorator_factory")
            & ~pl.col("has_starred_arguments")
            & (pl.col("argument_count") == 1)
            & pl.col("qualified_name").str.split(".").list.last().is_in(transformation_names)
            & ~pl.col("qualified_name").is_in(ignored_callables)
            & ~first_party_match
        )
        .with_columns(
            pl.when(pl.col("node_end_line") > pl.col("node_start_line"))
            .then(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("node_path"),
                    pl.lit(":"),
                    pl.col("node_start_line"),
                    pl.lit("-"),
                    pl.col("node_end_line"),
                    pl.lit("`"),
                )
            )
            .otherwise(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("node_path"),
                    pl.lit(":"),
                    pl.col("node_start_line"),
                    pl.lit("`"),
                )
            )
            .alias("location")
        )
    )
    repeated = (
        eligible.group_by("qualified_name", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("group_count"),
            pl.col("path").n_unique().cast(pl.UInt64).alias("file_count"),
            pl.col("location")
            .sort_by(["fact_order", "ordinal"])
            .str.join(", ")
            .alias("locations"),
            pl.col("fact_id").sort_by(["fact_order", "ordinal"]).first().alias("fact_id"),
            pl.col("ordinal").sort_by(["fact_order", "ordinal"]).first().alias("first_ordinal"),
            pl.col("node_path").sort_by(["fact_order", "ordinal"]).first().alias("path"),
            pl.col("node_start_line")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("start_line"),
            pl.col("node_start_column")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("start_column"),
            pl.col("node_end_line").sort_by(["fact_order", "ordinal"]).first().alias("end_line"),
            pl.col("node_end_column")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("end_column"),
        )
        .filter(
            (pl.col("group_count") >= minimum_repetitions)
            & (pl.col("file_count") >= minimum_files)
        )
        .sort("qualified_name")
        .with_row_index("finding_order")
    )
    counts = repeated.group_by("fact_id", maintain_order=True).agg(
        pl.col("group_count").sum().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = repeated.join(evidence, on="fact_id", how="left").with_columns(
        pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("external boundary candidate `"),
                pl.col("qualified_name"),
                pl.lit("` repeats "),
                pl.col("group_count"),
                pl.lit(" times across "),
                pl.col("file_count"),
                pl.lit(" files at "),
                pl.col("locations"),
            ),
            (
                ("external unary calls", pl.col("group_count"), Unit.COUNT),
                ("files using the callable", pl.col("file_count"), Unit.COUNT),
            ),
            finding_order=pl.col("finding_order"),
            evidence=pl.col("evidence"),
        ),
    )
