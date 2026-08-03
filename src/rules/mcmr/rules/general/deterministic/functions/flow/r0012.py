import polars as pl
from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......facts import ControlKind, FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table

_NESTING_KINDS = [
    ControlKind.CONDITIONAL,
    ControlKind.LOOP,
    ControlKind.SWITCH,
    ControlKind.CATCH,
]


@rule("ALL-FUNC0008", policy=Numeric(maximum=8))
def cognitive_complexity(
    subject: Table[FunctionFact], *, nesting_penalty: NonNegativeInt = 1
) -> CountQuery:
    """Measure how hard one callable is to follow, counting nesting against it.

    Definition
    ----------
    Score the control structures a provider resolved inside one callable. Every structure that
    breaks the linear flow adds one. A structure that also nests adds `nesting_penalty` for each
    enclosing structure it sits inside. A jump, a recursion, and a sequence of mixed Boolean
    operators add one without a nesting penalty, because they interrupt reading without adding a
    level to hold in mind. An alternative arm such as `else` or `elif` adds one on its own since a
    reader must carry the earlier condition into it.

    The measure is deliberately not cyclomatic complexity. A `switch` over twenty cases reads far
    more easily than three nested conditions, and only a nesting-aware score says so. The provider
    resolves what the structures are and how deep each one sits, and this rule owns the model, so
    the same score is comparable across every language a provider supports.

    Evidence
    --------
    Each finding records the callable range and every scored structure with its kind, its nesting
    depth, and the increment it contributed. The value is the total score.

    Exceptions
    ----------
    A callable whose structures a provider could not resolve scores zero rather than a guess. The
    score is a measurement and a project policy decides the acceptable ceiling, which differs
    between a parser, a request handler, and a test.

    Examples
    --------
    A callable holding one loop with one condition inside it returns `3`, which is one for the
    loop, one for the condition, and one because the condition nests inside the loop. The same two
    structures written in sequence return `2`. A callable with no control structure at all returns
    `0`.

    References
    ----------
    Cites "Cognitive Complexity", a new way of measuring understandability
    https://www.sonarsource.com/docs/CognitiveComplexity.pdf
    Generalizes clang-tidy readability-function-cognitive-complexity
    https://clang.llvm.org/extra/clang-tidy/checks/readability/function-cognitive-complexity.html
    Generalizes Clippy cognitive_complexity
    https://rust-lang.github.io/rust-clippy/master/index.html#cognitive_complexity
    """
    control_scores = (
        subject.lazy(FunctionRelation.CONTROLS)
        .group_by("function_id")
        .agg(
            pl.len().cast(pl.UInt64).alias("control_count"),
            pl.col("nesting_depth")
            .filter(pl.col("kind").is_in([str(kind) for kind in _NESTING_KINDS]))
            .sum()
            .alias("nesting_sum"),
        )
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            control_scores,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(
            pl.col("control_count").fill_null(0),
            pl.col("nesting_sum").fill_null(0),
        )
    )
    value = pl.col("control_count") + pl.col("nesting_sum") * nesting_penalty
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(frame, value, "cognitive complexity"),
    )
