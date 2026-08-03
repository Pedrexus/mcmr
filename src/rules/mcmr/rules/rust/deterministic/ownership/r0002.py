import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import RustSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from ..surfaces import RustRelations


@rule("RS-OWNE0002", policy=Numeric())
def clone_call_count(subject: Table[RustSurfaceFact]) -> CountQuery:
    """Count explicit copies one module makes.

    Definition
    ----------
    Report every `clone` and `to_owned` in one module. Like the lifetime count this is a
    measurement rather than a defect, and it is the other half of the same trade. Owning data keeps
    lifetimes out of signatures, and every copy is what that costs, so a module with no annotations
    and a hundred copies has not simplified anything. It has moved the complexity somewhere the
    type system stopped reporting it.

    Read the two numbers together. A module low in both has found a shape where ownership follows
    the work. A module low in one and high in the other has picked a side, which is a decision
    worth having made on purpose.

    Evidence
    --------
    Each finding names the value copied, the function it sits in, and the line, beside how many
    lifetimes the same module states so the trade is readable from either side. No repair is
    offered, since which way a module should lean is the project's decision. The value is the
    number of copies.

    Exceptions
    ----------
    A copy of a reference-counted handle is nearly free and is the recommended way to share
    ownership, so a project leaning on `Rc` or `Arc` raises this ceiling rather than fighting it. A
    copy at a boundary, where an owned value is handed to something that outlives the caller, is a
    copy that has to happen.

    Examples
    --------
    A module that clones a configuration once at startup returns `1`. A module that clones the same
    string in twelve helpers returns `12`, which is what says the string wanted to be owned by
    something higher up. A module that borrows throughout returns `0`.

    References
    ----------
    Generalizes Clippy redundant_clone
    https://rust-lang.github.io/rust-clippy/master/index.html#redundant_clone
    Cites "The Rust Performance Book", heap allocations
    https://nnethercote.github.io/perf-book/heap-allocations.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    relations = RustRelations(subject)
    clones = relations.records("clones")
    facts = relations.facts().with_columns(pl.col("clones.length").cast(pl.UInt64).alias("value"))
    selected = relations.located(clones)
    owner = pl.when(pl.col("owner") == "").then(pl.col("path")).otherwise(pl.col("owner"))
    receiver = (
        pl.when(pl.col("receiver") == "").then(pl.lit("a value")).otherwise(pl.col("receiver"))
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
                pl.lit("` explicitly"),
            ),
            (
                ("loops around it", pl.col("loop_depth"), Unit.COUNT),
                (
                    "lifetimes this module states",
                    pl.col("annotations.length"),
                    Unit.COUNT,
                ),
            ),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
