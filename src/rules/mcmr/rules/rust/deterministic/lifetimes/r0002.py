import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import RustSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from ..surfaces import RustRelations


@rule("RS-LIFE0002")
def demanded_static_lifetime(subject: Table[RustSurfaceFact]) -> CountQuery:
    """Count parameters and fields that demand data pinned for the whole run of the program.

    Definition
    ----------
    Report each `'static` written as the lifetime of a reference a parameter takes or a field
    holds. A `'static` reference does not say the data lives a long time. It says the data lives
    forever, which is a claim only a literal, a leak, or a global can honestly make, and demanding
    it of a caller is how the annotation wins an argument with the borrow checker by making the
    type unable to hold anything the caller owns.

    Where the pin sits decides whether it costs anything. A parameter typed `&'static str` cannot
    be handed a name read from a file and a field typed the same way cannot store one, and neither
    limitation is visible at the call site until someone tries. A return typed `&'static str` is
    the opposite, since it promises the caller more than it had to, forecloses nothing, and is how
    a lookup table hands back a name without allocating. Only the demanding side is reported.

    Evidence
    --------
    Each finding names the declaration that demands the pin and the line it is written on, and
    states how many pins the module holds in total so a reader can see what share demands. The
    repair is a choice, since owning the data and keeping the pin honestly are both real answers.
    The value is the number of demanding pins.

    Exceptions
    ----------
    A `T: 'static` bound is not counted, because a bound says what a type may not borrow rather
    than pinning any particular value, and a thread, a task, or a trait object often requires one.
    A return position is not counted, because promising a longer lifetime than required takes
    nothing away from a caller. A field that genuinely holds a compile-time table, and an interner
    that leaks on purpose, both demand honestly, and a project excludes those rather than owning
    data it never frees.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       struct Report { title: &'static str }
       fn describe(name: &'static str) -> Report { ... }

    Good
    ~~~~
    .. code-block:: rust

       struct Report { title: String }
       fn describe(name: &str) -> Report { ... }

    A `fn label(kind: Kind) -> &'static str` returning one of a fixed set of names is not reported,
    because the names really do live in the binary and the caller gains by being told so.

    References
    ----------
    Cites "The Rust Reference", static lifetime
    https://doc.rust-lang.org/reference/lifetime-elision.html#static-lifetime-elision
    Cites "Rust by Example", the static lifetime and its two meanings
    https://doc.rust-lang.org/rust-by-example/scope/lifetime/static_lifetime.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    relations = RustRelations(subject)
    demanding = relations.records("pins").filter(pl.col("position") == "demand")
    facts = relations.counted(demanding)
    selected = relations.located(demanding).join(
        facts.select("fact_id", "value"),
        on="fact_id",
        how="inner",
    )
    owner = pl.when(pl.col("owner") == "").then(pl.col("path")).otherwise(pl.col("owner"))
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                owner,
                pl.lit(
                    "` demands a `'static` reference, so no caller can hand it anything read at "
                    "run time"
                ),
            ),
            (
                ("pins demanding here", pl.col("value"), Unit.COUNT),
                ("pins this module states", pl.col("pins.length"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("decide what `"),
                owner,
                pl.lit("` may be handed"),
            ),
            options=(
                "take an owned value so a caller can build one",
                "keep the pin where only a literal or a leak can honestly satisfy it",
            ),
            evidence=pl.col("evidence"),
        ),
    )
