import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import RustSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from ..surfaces import RustRelations

# Rust states elision rules only for functions and methods. Other declarations name lifetimes the
# compiler cannot infer, so the rule has no comparison to make.
_ELIDING_KINDS = {"function", "method"}


@rule("RS-LIFE0001")
def elidable_lifetime_annotation(subject: Table[RustSurfaceFact]) -> CountQuery:
    """Count lifetime annotations the compiler would have inferred on its own.

    Definition
    ----------
    Read every signature that names a lifetime and report one whose elided form means exactly the
    same thing. Elision gives each input lifetime position its own fresh lifetime and gives every
    elided output the receiver's lifetime, so an annotation restating that tells the reader nothing
    the compiler did not already know and charges them the reading anyway.

    The cost is not the character count. A signature carrying `<'a>` reads as a signature with a
    borrowing constraint worth understanding, so the reader stops and works out which one. Doing
    that and finding nothing is worse than never having stopped.

    Two arrangements are claimed and both are settled by the signature alone. A lifetime written
    in exactly one input position and read nowhere else is one elision produces identically. A
    lifetime the receiver carries and the return states is another, since elision hands every
    elided output the receiver's lifetime whatever else is in scope.

    Evidence
    --------
    Each finding names the declaration, the lifetimes it states, and the line it states them on,
    and counts the input positions those lifetimes appear in. The repair is a choice, because
    deleting the annotation and keeping it for a reason the signature cannot show are both real
    answers. The value is the number of annotations elision would have produced identically.

    Exceptions
    ----------
    A type, a trait, and an alias are not judged at all, because Rust states no elision rule for
    any of them and there is nothing to compare their annotation against.

    A lifetime written in two input positions is never reported even where it reaches no output,
    because tying two inputs together is a constraint elision cannot state and the two signatures
    therefore do not mean the same thing. Where the body relies on the tie, deleting the annotation
    does not compile at all.

    An output lifetime coming from one input with no receiver is left alone as well. It turns on
    how many lifetime positions the inputs hold in total, and a bare `Node` hides one where `&str`
    shows it, so the arity lives in the type definitions rather than in the signature. Clippy reads
    those definitions and reports that arrangement, and guessing at it here would mean reporting a
    signature that does not compile without its annotation.

    Stable Rust also requires a lifetime used in an associated type binding under argument-position
    `impl Trait` to be named. That annotation is syntax the compiler demands rather than optional
    documentation, so the provider marks it and this rule leaves it alone.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       fn name<'a>(&'a self) -> &'a str { ... }
       fn width<'a>(text: &'a str) -> usize { ... }

    Good
    ~~~~
    .. code-block:: rust

       fn name(&self) -> &str { ... }
       fn width(text: &str) -> usize { ... }

    A lifetime that survives is one elision would get wrong, such as
    `fn pick<'a>(&self, other: &'a str) -> &'a str`, where the elided output would borrow from
    `self` instead, or `fn descend<'a>(node: &'a Node, found: &mut Vec<&'a Node>)`, where both
    inputs have to name one lifetime for the body to compile at all.

    References
    ----------
    Cites "The Rust Reference", lifetime elision
    https://doc.rust-lang.org/reference/lifetime-elision.html
    Cites "Rust API Guidelines", C-STRUCT-BOUNDS and the cost of stating what is inferred
    https://rust-lang.github.io/api-guidelines/future-proofing.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    relations = RustRelations(subject)
    selected_annotations = _LifetimeElision(relations).annotations()
    facts = relations.counted(selected_annotations)
    selected = relations.located(selected_annotations)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("owner"),
                pl.lit("` names "),
                pl.col("stated_names"),
                pl.lit(", which elision would have produced on its own"),
            ),
            (
                ("lifetimes it states", pl.col("names.length"), Unit.COUNT),
                (
                    "input positions naming one",
                    pl.col("parameters.length") + (pl.col("receiver") != "").cast(pl.UInt64),
                    Unit.COUNT,
                ),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("say what `"),
                pl.col("owner"),
                pl.lit("` gains from writing "),
                pl.col("stated_names"),
            ),
            options=(
                "delete the annotation and let elision state the same signature",
                "keep it where a reader needs the borrow named",
            ),
            evidence=pl.col("evidence"),
        ),
    )


class _LifetimeElision:
    """Select annotations whose named lifetimes match Rust's elision rules."""

    def __init__(self, relations: RustRelations) -> None:
        self.relations = relations

    def annotations(self) -> pl.LazyFrame:
        """Return annotations for which every named lifetime is inferred identically."""
        annotations = self.relations.annotations().filter(
            pl.col("kind").is_in(list(_ELIDING_KINDS)) & (pl.col("names.length") > 0)
        )
        inferred = self.inferred_names(annotations)
        eligible = inferred.group_by("parent_id").agg(
            pl.col("inferred").all().alias("all_inferred")
        )
        return annotations.join(
            eligible,
            left_on="record_id",
            right_on="parent_id",
            how="inner",
        ).filter(pl.col("all_inferred"))

    def inferred_names(self, annotations: pl.LazyFrame) -> pl.LazyFrame:
        """State whether elision places each declared name exactly as written."""
        names = self.relations.values("annotations.names").select(
            "parent_id",
            pl.col("string_value").alias("name"),
        )
        parameters = (
            self.relations.values("annotations.parameters")
            .group_by("parent_id", "string_value")
            .agg(pl.len().cast(pl.UInt64).alias("parameter_count"))
            .rename({"string_value": "name"})
        )
        returned = self.relations.values("annotations.returned")
        returned_totals = returned.group_by("parent_id").agg(
            pl.len().cast(pl.UInt64).alias("returned_count")
        )
        matching_returns = (
            returned.group_by("parent_id", "string_value")
            .agg(pl.len().cast(pl.UInt64).alias("matching_return_count"))
            .rename({"string_value": "name"})
        )
        beyond = self.marker("annotations.beyond", name="beyond")
        required = self.marker(
            "annotations.required_by_syntax",
            name="required_by_syntax",
        )
        named = (
            names.join(
                annotations.select(
                    pl.col("record_id").alias("parent_id"),
                    "receiver",
                ),
                on="parent_id",
                how="inner",
            )
            .join(parameters, on=["parent_id", "name"], how="left")
            .join(returned_totals, on="parent_id", how="left")
            .join(matching_returns, on=["parent_id", "name"], how="left")
            .join(beyond, on=["parent_id", "name"], how="left")
            .join(required, on=["parent_id", "name"], how="left")
            .with_columns(
                pl.col(
                    "parameter_count",
                    "returned_count",
                    "matching_return_count",
                ).fill_null(0)
            )
        )
        inputs = pl.col("parameter_count") + (pl.col("receiver") == pl.col("name")).cast(pl.UInt64)
        return named.with_columns(
            (
                (pl.col("name") != "static")
                & ~pl.col("beyond").fill_null(False)
                & ~pl.col("required_by_syntax").fill_null(False)
                & pl.when(pl.col("matching_return_count") == 0)
                .then(inputs == 1)
                .otherwise(
                    (pl.col("receiver") == pl.col("name"))
                    & (inputs == 1)
                    & (pl.col("matching_return_count") == pl.col("returned_count"))
                )
            ).alias("inferred")
        )

    def marker(self, relation: str, *, name: str) -> pl.LazyFrame:
        """Return a keyed Boolean marker for one named lifetime relation."""
        return self.relations.values(relation).select(
            "parent_id",
            pl.col("string_value").alias("name"),
            pl.lit(True).alias(name),
        )
