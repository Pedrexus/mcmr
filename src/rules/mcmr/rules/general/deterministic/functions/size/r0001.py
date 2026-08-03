import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0001", policy=Numeric(maximum=10))
def function_statement_count(
    subject: Table[FunctionFact],
) -> CountQuery:
    """Limit direct statements in one callable body.

    Definition
    ----------
    Count statements directly owned by each function, method, or nested function after removing
    its docstring. Statements inside an owned branch remain part of the branch statement rather
    than being counted twice. Declarative query bodies are excluded because they describe one
    relational plan rather than a sequence of host operations.

    Evidence
    --------
    The finding names the callable, its exact source span, and its direct statement count. The
    value is that statement count. A project may override the rule-owned ceiling of ten.

    Exceptions
    ----------
    A generated, vendored, or framework-constrained body is long for a reason nobody in this
    repository can change, so provider selection is where those are excluded. A cohesive numerical
    kernel or protocol adapter may need more than ten steps. Exclude that exact path only after
    checking that named sections would not make the algorithm easier to follow.

    Examples
    --------
    A function with eleven direct statements returns `11` and fails. A function with one `if`
    whose branches contain several statements returns `1` here while complexity rules measure the
    nested control flow.

    References
    ----------
    Cites "Clean Code", chapter 3, Functions
    Cites Ruff PLR0915 too-many-statements
    https://docs.astral.sh/ruff/rules/too-many-statements/
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    frame = subject.lazy(FunctionRelation.FUNCTIONS).filter(~pl.col("is_declarative_body"))
    statements = pl.col("direct_statement_count")
    return RuleQuery.integer(
        frame,
        statements,
        findings=FindingQuery.build(
            frame,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` owns "),
                statements,
                pl.when(statements == 1)
                .then(pl.lit(" direct statement"))
                .otherwise(pl.lit(" direct statements")),
            ),
            (
                ("direct statements", statements, Unit.COUNT),
                ("implementation lines", pl.col("implementation_lines"), Unit.COUNT),
            ),
            question=pl.concat_str(
                pl.lit("extract one named step from `"),
                pl.col("name"),
                pl.lit("`"),
            ),
            options=(
                "extract a cohesive section",
                "accept the count for one indivisible algorithm",
            ),
        ),
    )
