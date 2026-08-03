import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table


@rule("ALL-ERRO0003")
def vanilla_error_type(
    subject: Table[SyntaxFact],
    *,
    base_errors: tuple[str, ...] = (
        "Exception",
        "BaseException",
        "Error",
        "Throwable",
        "RuntimeException",
        "std::exception",
    ),
) -> RuleQuery[int]:
    """Count failures raised as the language base error rather than as a named one.

    Definition
    ----------
    Read every raise one declaration states, take the type it names, and report the ones that
    name the base error the language ships. That is `Exception` and `BaseException` in Python,
    `Error` in JavaScript and TypeScript, `Throwable` and `RuntimeException` in Java, and
    `std::exception` in C++. A name that arrives qualified is judged on its last segment, so
    `builtins.Exception` reads the same as `Exception`.

    The cost lands on the caller rather than on the raiser. Handling this one failure means
    catching the base type, which also catches the typo, the missing key, and the bug three
    frames down, so the caller either swallows defects it never meant to see or gives up on
    recovery and lets everything through. A named type costs one line to declare and it turns
    the catch into a statement about what went wrong instead of a statement about anything at
    all going wrong.

    Evidence
    --------
    Each finding names the declaration, the raise, and the base type it constructs. The value is
    the number of raises a caller cannot single out.

    Exceptions
    ----------
    A bare re-raise carries the original type forward and constructs nothing, so it is left alone,
    and so is a raise of a value the code already holds such as a failure it caught a line above.
    The base names are a setting, because a project that declares its own root error may want that
    name reported too, and a language MCMR has not met yet spells its base differently. Only a
    callable is judged, because a type reaches every raise it owns through the callable holding it
    and would otherwise report the same one twice. `base_errors` is that list of names.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def load(path):
           if not path.exists():
               raise Exception(f"{path} is missing")

    Good
    ~~~~
    .. code-block:: python

       def load(path):
           if not path.exists():
               raise ProfileMissing(path)

    References
    ----------
    Generalizes Ruff TRY002 raise-vanilla-class
    https://docs.astral.sh/ruff/rules/raise-vanilla-class/
    Cites Pylint W0719 broad-exception-raised
    https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/broad-exception-raised.html
    Cites "The Python Tutorial", user defined exceptions
    https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions
    Cites "Clean Code", chapter 7, define exceptions in terms of a caller's needs
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = subject.lazy(SyntaxRelation.NODES)
    raises = nodes.filter(pl.col("kind") == "raise").select(
        "fact_id",
        pl.col("ordinal").alias("raise_ordinal"),
        pl.col("subtree_end").alias("raise_end"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    )
    expressions = nodes.filter(pl.col("kind").is_in(["call", "name"])).select(
        "fact_id",
        "ordinal",
        pl.col("name").str.split(".").list.last().alias("thrown"),
    )
    reported = (
        raises.join(expressions, on="fact_id", how="inner")
        .filter(
            (pl.col("ordinal") >= pl.col("raise_ordinal"))
            & (pl.col("ordinal") < pl.col("raise_end"))
        )
        .group_by("fact_id", "raise_ordinal", maintain_order=True)
        .agg(
            pl.col("thrown").sort_by("ordinal").first(),
            pl.col("path").first(),
            pl.col("start_line").first(),
            pl.col("start_column").first(),
            pl.col("end_line").first(),
            pl.col("end_column").first(),
        )
        .filter(pl.col("thrown").is_in(list(base_errors)))
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.lit("raise constructs the base error `"),
            pl.col("thrown"),
            pl.lit("`"),
        ),
        (("vanilla error type", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("raise_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
