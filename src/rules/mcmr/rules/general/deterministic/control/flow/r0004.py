import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table


@rule("ALL-CONT0004")
def deeply_nested_body(
    subject: Table[SyntaxFact],
    *,
    maximum_depth: NonNegativeInt = 3,
    body_kinds: tuple[str, ...] = ("branch", "loop", "guard", "scope"),
) -> RuleQuery[bool]:
    """Whether one declaration nests bodies deeper than the ceiling a reader can hold.

    Definition
    ----------
    Walk the declaration and find the longest chain of constructs that open a body inside another
    body, counting a branch, a loop, a guarded block, and a scope. Report the declaration when that
    chain passes `maximum_depth`. Each level is a condition a reader has to carry from the line
    that opened it all the way down, and by the fourth level the line in front of them only makes
    sense together with three others somewhere above.

    A construct only adds a level where it is written deeper than the one holding it, which is the
    reader's own measure since indentation is what nesting looks like on the page. That is what
    keeps a chain of alternatives flat. Python spells the chain `elif` and hands over one branch,
    while Rust and C spell it `} else if {` and hand over a branch inside a branch, yet both read
    as one decision with several arms and neither costs a reader a level.

    Nesting is also where bugs hide, because the deepest line is the one reached by the fewest
    inputs and therefore the one a test is least likely to run. The usual repair is a guard clause
    that returns early, or lifting the innermost body into a function that names what it does.

    Evidence
    --------
    Each finding names the declaration and the deepest chain it holds, with the line each level
    opens on. The result is true for one declaration that nests too deeply.

    Exceptions
    ----------
    Expression structure is not nesting, so a call inside a comparison inside an argument counts
    nothing, and only a construct opening a body is counted. An arm of a chained alternative is not
    a level either, since it closes where the branch it continues closes and is never written
    deeper than it. Traversal carries its own stack, so the interpreter's recursion setting never
    becomes a private depth ceiling. A construct a frontend states without a span is measured as
    written, because nothing then locates it against what holds it. A declaration whose family was
    never asked for carries no tree and is not judged. `body_kinds` names the constructs that open
    a body, so a language whose block construct this list has not met is configured rather than
    reimplemented.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def settle(orders):
           for order in orders:
               if order.is_open:
                   for item in order.items:
                       if item.is_taxed:
                           charge(item)

    Good
    ~~~~
    .. code-block:: python

       def settle(orders):
           for order in orders:
               if order.is_open:
                   settle_items(order)

       def settle_items(order):
           for item in order.items:
               if item.is_taxed:
                   charge(item)

    References
    ----------
    Generalizes SonarSource S134
    https://rules.sonarsource.com/python/RSPEC-134/
    Cites "Cognitive Complexity", a new way of measuring understandability
    https://www.sonarsource.com/resources/cognitive-complexity/
    Generalizes Clippy excessive_nesting
    https://rust-lang.github.io/rust-clippy/master/index.html#excessive_nesting
    Cites Ruff SIM102 collapsible-if
    https://docs.astral.sh/ruff/rules/collapsible-if/
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = subject.lazy(SyntaxRelation.NODES)
    parents = nodes.select(
        "fact_id",
        pl.col("ordinal").alias("parent_ordinal"),
        pl.col("end_line").alias("parent_end_line"),
        pl.col("end_column").alias("parent_end_column"),
        pl.col("start_column").alias("parent_start_column"),
    )
    bodies = (
        nodes.filter(pl.col("kind").is_in(list(body_kinds)))
        .join(
            subject.lazy(SyntaxRelation.CHILDREN).select(
                "fact_id", "parent_ordinal", pl.col("child_ordinal").alias("ordinal")
            ),
            on=["fact_id", "ordinal"],
            how="left",
        )
        .join(parents, on=["fact_id", "parent_ordinal"], how="left")
        .with_columns(
            (
                ~(
                    pl.col("parent_ordinal").is_not_null()
                    & (pl.col("end_line") == pl.col("parent_end_line"))
                    & (pl.col("end_column") == pl.col("parent_end_column"))
                    & (pl.col("start_column") <= pl.col("parent_start_column"))
                )
            )
            .cast(pl.UInt64)
            .alias("increment")
        )
        .select("fact_id", "ordinal", "subtree_end", "increment")
    )
    targets = bodies.select("fact_id", pl.col("ordinal").alias("target_ordinal"))
    depths = (
        targets.join(
            bodies.select(
                "fact_id",
                pl.col("ordinal").alias("ancestor_ordinal"),
                pl.col("subtree_end").alias("ancestor_end"),
                "increment",
            ),
            on="fact_id",
            how="inner",
        )
        .filter(
            (pl.col("ancestor_ordinal") <= pl.col("target_ordinal"))
            & (pl.col("target_ordinal") < pl.col("ancestor_end"))
        )
        .group_by("fact_id", "target_ordinal", maintain_order=True)
        .agg(pl.col("increment").sum().alias("depth"))
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("depth").max())
    )
    values = facts.join(depths, on="fact_id", how="left").with_columns(
        pl.col("depth").fill_null(0)
    )
    exceeds = pl.col("depth") > maximum_depth
    findings = FindingQuery.build(
        values,
        pl.concat_str(
            pl.lit("`"),
            pl.when(pl.col("qualname") != "")
            .then(pl.col("qualname"))
            .otherwise(pl.col("fact_id")),
            pl.lit("` nests bodies "),
            pl.col("depth"),
            pl.lit(" levels deep, past the ceiling of "),
            pl.lit(maximum_depth),
        ),
        (
            ("body nesting depth", pl.col("depth"), Unit.COUNT),
            ("maximum body nesting depth", pl.lit(maximum_depth), Unit.COUNT),
        ),
        predicate=exceeds,
    )
    return RuleQuery.boolean(values, exceeds, findings=findings)
