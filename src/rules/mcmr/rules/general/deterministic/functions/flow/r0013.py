import polars as pl

from ...... import Numeric, rule
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0009", policy=Numeric(maximum=2))
def nesting_depth(subject: Table[FunctionFact]) -> CountQuery:
    """Measure the deepest control nesting one callable reaches.

    Definition
    ----------
    Read the nesting depth a provider recorded for every control structure inside one callable and
    return the deepest one. Depth counts the structures enclosing a structure rather than the
    structure itself, so the outermost loop of a body sits at depth zero and a condition written
    inside it sits at depth one. Depth is what forces a reader to hold earlier conditions in mind
    while reading the innermost statement, which is why it is measured on its own rather than
    folded into a single complexity number.

    Evidence
    --------
    Each finding records the callable range and the deepest structure with its own range. The value
    is that depth.

    Exceptions
    ----------
    A callable with no resolved control structure has depth zero. Guard clauses that return early
    keep depth low by construction and are the usual repair, so the measurement rewards them
    without naming them.

    Examples
    --------
    A loop holding a condition holding a second condition returns `2`, since the loop is at depth
    zero and the two conditions at depths one and two. The same logic written as three sequential
    guard clauses returns `0`, because no structure encloses another. A callable with no control
    structure at all also returns `0`.

    References
    ----------
    Generalizes Clippy excessive_nesting
    https://rust-lang.github.io/rust-clippy/master/index.html#excessive_nesting
    Generalizes ESLint max-depth
    https://eslint.org/docs/latest/rules/max-depth
    Cites Pylint R1702 too-many-nested-blocks
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-nested-blocks.html
    """
    depths = (
        subject.lazy(FunctionRelation.CONTROLS)
        .group_by("function_id")
        .agg(pl.col("nesting_depth").max())
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            depths,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("nesting_depth").fill_null(0))
    )
    value = pl.col("nesting_depth")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(frame, value, "nesting depth"),
    )
