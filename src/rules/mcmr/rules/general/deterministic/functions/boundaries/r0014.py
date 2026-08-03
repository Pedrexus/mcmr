import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0010", policy=Numeric(maximum=5))
def required_parameter_count(subject: Table[FunctionFact]) -> CountQuery:
    """Count the inputs a caller must supply to one callable.

    Definition
    ----------
    Count the declared parameters that carry no default and are not the receiver. A long required
    list is the readable symptom of a callable that owns several responsibilities, or of a missing
    type that should carry the values together. The count excludes optional parameters because a
    caller never has to think about them, and excludes the receiver because it is not a decision
    the caller makes.

    Evidence
    --------
    The finding records the callable range, every counted parameter by name, and how many of the
    declared parameters those required ones are. It is stated for every callable rather than only
    for a wide one, because the measurement is the whole answer and a reader has to be able to see
    which inputs it counted. The value is the number of required inputs.

    Exceptions
    ----------
    A constructor that assembles a value from its parts, a mathematical function over independent
    scalars, and a framework entry point with a fixed contract all legitimately take several
    inputs. The count is a measurement and the policy owns the ceiling.

    Examples
    --------
    `def render(template, context, encoding="utf-8")` returns `2`. A method whose only parameter is
    its receiver returns `0`.

    References
    ----------
    Generalizes Clippy too_many_arguments
    https://rust-lang.github.io/rust-clippy/master/index.html#too_many_arguments
    Generalizes typescript-eslint max-params
    https://typescript-eslint.io/rules/max-params/
    Cites Pylint R0913 too-many-arguments
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-arguments.html
    """
    parameters = subject.lazy(FunctionRelation.PARAMETERS)
    declared = parameters.group_by("function_id").agg(
        pl.len().cast(pl.UInt64).alias("parameter_count")
    )
    required = (
        parameters.filter(~pl.col("is_receiver") & pl.col("is_required_by_external_contract"))
        .sort("function_id", "ordinal")
        .group_by("function_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("required_count"),
            pl.col("name").str.join("`, `").alias("required_names"),
        )
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(declared, left_on="entity_id", right_on="function_id", how="left")
        .join(required, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(
            pl.col("parameter_count").fill_null(0),
            pl.col("required_count").fill_null(0),
        )
    )
    value = pl.col("required_count")
    parameter_phrase = (
        pl.when(value == 1)
        .then(pl.lit("1 parameter"))
        .otherwise(pl.concat_str(value, pl.lit(" parameters")))
    )
    declared_phrase = (
        pl.when(pl.col("parameter_count") == 1)
        .then(pl.lit("1 parameter"))
        .otherwise(pl.concat_str(pl.col("parameter_count"), pl.lit(" parameters")))
    )
    message = (
        pl.when(value > 0)
        .then(
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` cannot be called without `"),
                pl.col("required_names"),
                pl.lit("`, which is "),
                parameter_phrase,
                pl.lit(" of the "),
                pl.col("parameter_count"),
                pl.lit(" it declares"),
            )
        )
        .otherwise(
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` can be called with nothing, since none of the "),
                declared_phrase,
                pl.lit(" it declares is required"),
            )
        )
    )
    findings = FindingQuery.build(
        frame,
        message,
        (
            ("parameters a caller has to supply", value, Unit.COUNT),
            ("parameters declared", pl.col("parameter_count"), Unit.COUNT),
        ),
        question=pl.concat_str(pl.lit("ask `"), pl.col("name"), pl.lit("` for less")),
        options=(
            "group the inputs that always travel together into one type",
            "default the ones a caller almost never chooses",
        ),
    )
    return RuleQuery.integer(
        frame,
        value,
        findings=findings,
    )
