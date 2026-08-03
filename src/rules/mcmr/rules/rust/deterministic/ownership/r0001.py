import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import RustSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from ..surfaces import RustRelations


@rule("RS-OWNE0001", policy=Numeric())
def clone_inside_loop(subject: Table[RustSurfaceFact]) -> CountQuery:
    """Count explicit copies made inside loops.

    Definition
    ----------
    Report each `clone` or `to_owned` written inside a `for`, `while`, or `loop` body. This is a
    measurement because syntax alone cannot distinguish a redundant copy from ownership transferred
    into one result per iteration. Projects may set a ceiling when repeated copies are unwanted.

    This is the counterpart to the lifetime rules. Removing an annotation by owning the data is
    usually right, and this is the one place where it usually is not.

    Evidence
    --------
    Each finding names the value copied, the function it sits in, the line, and how deeply nested
    the loop around it is. The repair is a choice, because hoisting the copy and borrowing across
    the loop are different edits and only the body says which one holds. The value is the number of
    copies made inside a loop.

    Exceptions
    ----------
    A copy of something the loop then consumes, such as an owned value handed to a spawned task or
    pushed into a collection that outlives the iteration, is a copy that has to happen. A cheap
    copy of a small value is a copy the compiler often removes, and measuring is what settles it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       for item in items {
           registry.insert(prefix.clone(), item);
       }

    Good
    ~~~~
    .. code-block:: rust

       let prefix = prefix.clone();
       for item in items {
           registry.insert(prefix.as_str(), item);
       }

    References
    ----------
    Cites Clippy redundant_clone
    https://rust-lang.github.io/rust-clippy/master/index.html#redundant_clone
    Cites "The Rust Performance Book", allocations in hot loops
    https://nnethercote.github.io/perf-book/heap-allocations.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    relations = RustRelations(subject)
    repeated = relations.records("clones").filter(pl.col("loop_depth") > 0)
    facts = relations.counted(repeated)
    selected = relations.located(repeated)
    owner = pl.when(pl.col("owner") == "").then(pl.col("path")).otherwise(pl.col("owner"))
    receiver = (
        pl.when(pl.col("receiver") == "").then(pl.lit("a value")).otherwise(pl.col("receiver"))
    )
    question_receiver = (
        pl.when(pl.col("receiver") == "").then(pl.lit("this value")).otherwise(pl.col("receiver"))
    )
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                owner,
                pl.lit("` copies `"),
                receiver,
                pl.lit("` inside a loop, so the copy is paid again on every pass"),
            ),
            (
                ("loops around it", pl.col("loop_depth"), Unit.COUNT),
                ("copies this module makes", pl.col("clones.length"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("pay for `"),
                question_receiver,
                pl.lit("` once rather than once a pass"),
            ),
            options=(
                "hoist the copy above the loop",
                "borrow across the loop instead",
                "keep it where the loop consumes what it copied",
            ),
            evidence=pl.col("evidence"),
        ),
    )
