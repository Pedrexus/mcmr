import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import RustSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from ..surfaces import RustRelations


@rule("RS-LIFE0003", policy=Numeric(maximum=2))
def lifetime_annotation_count(subject: Table[RustSurfaceFact]) -> CountQuery:
    """Count declarations that carry an explicit lifetime, elidable or not.

    Definition
    ----------
    Report every function, method, type, trait, and alias in one module that names a lifetime. This
    is a measurement rather than a defect, and it is deliberately opinionated, since a project that
    wants borrowing kept out of its interfaces sets the ceiling to zero, and one whose whole reason
    to exist is zero-copy sets it high. Both are answering the same question, which is how much of
    the borrow checker the readers of this module have to hold in their heads.

    Read it beside the clone count. Driving this number to zero by owning everything moves the cost
    into allocations, and driving allocations to zero by borrowing everything moves it into
    signatures. Neither number alone says whether the trade was made well.

    Evidence
    --------
    Each finding names the declaration, its kind, the lifetimes it states, and the line it states
    them on, beside how many copies the same module makes so the trade is readable from either
    side. No repair is offered, since which way a module should lean is the project's decision. The
    value is the number of declarations carrying a lifetime.

    Exceptions
    ----------
    A module that has to borrow, such as a parser handing out slices of the text it was given, is
    where the annotations belong, and its ceiling should say so. An annotation forced by a
    dependency is not a choice this project made and is a reason to exclude the module rather than
    to fight the signature.

    Examples
    --------
    A module with `struct Source<'a> { text: &'a str }` and two methods returning `&'a str`
    returns `3`. A module that owns its `String` and returns `&str` through elision returns `0`.

    References
    ----------
    Cites "The Rust Reference", lifetime elision
    https://doc.rust-lang.org/reference/lifetime-elision.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    Cites "Rust for Rustaceans", chapter on lifetimes in interfaces
    """
    relations = RustRelations(subject)
    facts = relations.facts().with_columns(
        pl.col("annotations.length").cast(pl.UInt64).alias("value")
    )
    selected = relations.located(relations.annotations())
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("owner"),
                pl.lit("` is a "),
                pl.col("kind"),
                pl.lit(" naming "),
                pl.col("stated_names"),
            ),
            (
                ("lifetimes it states", pl.col("names.length"), Unit.COUNT),
                ("copies this module makes", pl.col("clones.length"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
