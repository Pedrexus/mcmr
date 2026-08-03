import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table

# What a Boolean is called in each language a frontend fills. A parameter typed with any of these
# reads as a flag whatever it is named and wherever it sits in the list.
_BOOLEAN = ["bool", "boolean", "Boolean", "_Bool", "BOOL"]


@rule("ALL-PARA0004", policy=Numeric(maximum=1))
def boolean_parameter_count(subject: Table[FunctionFact]) -> CountQuery:
    """Count the flags one callable takes, wherever a caller passes them.

    Definition
    ----------
    Count every parameter a callable declares whose type is Boolean or whose default is Boolean,
    excluding the receiver a language passes implicitly. Each flag doubles the states the body has
    to be correct in, so three of them describe eight callables sharing one name and one test
    suite, and the ones nobody exercises are the ones that break.

    This counts a keyword-only flag as well as a positional one. Naming a flag at the call site
    fixes readability, which is what the neighbouring positional-flag rule is about, and it does
    nothing about the state space, which is what this rule measures. The repair here is to split
    the callable or to replace the flags with one closed set of named behaviors.

    The measure is language-neutral because a flag is. A Rust `fn` taking four `bool` parameters, a
    TypeScript function taking four `boolean` ones, and a Python function taking four annotated
    `bool` ones are one design decision spelled three ways, so one rule answers for all of them.

    Evidence
    --------
    Each finding records the callable range and every counted parameter with its declared type. The
    value is the number of Boolean parameters, and a project policy owns the ceiling.

    Exceptions
    ----------
    The receiver is never counted, since a caller does not choose it. A signature an external
    contract fixes, such as a framework callback or a trait implementation, is a reason to exclude
    the module rather than to fight the interface. A parameter typed as a closed set of two named
    values is not a Boolean and is not counted, which is exactly the repair this rule points at.

    Examples
    --------
    `def render(document, *, inline: bool, minified: bool, strict: bool)` returns `3`, and so does
    `fn render(document: &Document, inline: bool, minified: bool, strict: bool)`. Replacing them
    with one `mode: RenderMode` parameter returns `0`.

    References
    ----------
    Generalizes Clippy fn_params_excessive_bools
    https://rust-lang.github.io/rust-clippy/master/index.html#fn_params_excessive_bools
    Cites Ruff FBT001 boolean-type-hint-positional-argument
    Cites Ruff FBT002 boolean-default-value-positional-argument
    Cites "Refactoring", remove flag argument
    https://refactoring.com/catalog/removeFlagArgument.html
    Cites "Clean Code", chapter 3, flag arguments
    """
    parameters = subject.lazy(FunctionRelation.PARAMETERS)
    declared = parameters.group_by("function_id").agg(
        pl.len().cast(pl.UInt64).alias("parameter_count")
    )
    flags = (
        parameters.filter(
            ~pl.col("is_receiver")
            & (
                pl.col("type_name").is_in(_BOOLEAN)
                | pl.col("has_boolean_annotation")
                | pl.col("has_boolean_default")
            )
        )
        .with_columns(
            pl.when(pl.col("type_name") != "")
            .then(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("name"),
                    pl.lit("` as `"),
                    pl.col("type_name"),
                    pl.lit("`"),
                )
            )
            .when(pl.col("has_boolean_annotation"))
            .then(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("name"),
                    pl.lit("` with a Boolean annotation"),
                )
            )
            .otherwise(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("name"),
                    pl.lit("` with a Boolean default"),
                )
            )
            .alias("description")
        )
        .sort("function_id", "ordinal")
        .group_by("function_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("value"),
            pl.col("description").str.join(", ").alias("descriptions"),
        )
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(declared, left_on="entity_id", right_on="function_id", how="left")
        .join(flags, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(
            pl.col("parameter_count").fill_null(0),
            pl.col("value").fill_null(0),
        )
    )
    value = pl.col("value")
    combinations = pl.lit(2, dtype=pl.UInt64).pow(value)
    flag_phrase = (
        pl.when(value == 1)
        .then(pl.lit("1 Boolean parameter"))
        .otherwise(pl.concat_str(value, pl.lit(" Boolean parameters")))
    )
    combination_phrase = (
        pl.when(combinations == 1)
        .then(pl.lit("1 behavior combination"))
        .otherwise(pl.concat_str(combinations, pl.lit(" behavior combinations")))
    )
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit("` takes "),
            flag_phrase,
            pl.when(value == 1)
            .then(pl.lit(", which creates "))
            .otherwise(pl.lit(", which create ")),
            combination_phrase,
            pl.lit(", with "),
            pl.col("descriptions"),
        ),
        (
            ("Boolean parameters", value, Unit.COUNT),
            ("possible behavior combinations", combinations, Unit.COUNT),
            ("parameters declared", pl.col("parameter_count"), Unit.COUNT),
        ),
        predicate=value > 0,
        question=pl.concat_str(
            pl.lit("reduce the state space of `"),
            pl.col("name"),
            pl.lit("`"),
        ),
        options=(
            "split the callable by behavior",
            "replace the flags with one closed set of named behaviors",
        ),
    )
    return RuleQuery.integer(
        frame,
        value,
        findings=findings,
    )
