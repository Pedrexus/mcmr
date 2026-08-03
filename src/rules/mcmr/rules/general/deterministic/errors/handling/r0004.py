import re

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable


def _guards_and_clauses(
    relations: SyntaxTable, nodes: pl.LazyFrame, handlers: tuple[str, ...]
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Return located guards and the error names each handler states."""
    guards = relations.with_text(nodes.filter(pl.col("kind") == "guard")).select(
        "fact_id",
        pl.col("ordinal").alias("guard_ordinal"),
        pl.col("start_line").alias("guard_start_line"),
        pl.col("start_column").alias("guard_column"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("text").str.split("\n").alias("lines"),
    )
    lines = (
        guards.with_columns(pl.int_ranges(0, pl.col("lines").list.len()).alias("offset"))
        .explode("lines", "offset", empty_as_null=True)
        .with_columns(
            (
                pl.col("lines").str.len_chars()
                - pl.col("lines").str.strip_chars_start().str.len_chars()
            ).alias("indent")
        )
    )
    opening = r"^[}\t ]*(?:" + "|".join(map(re.escape, handlers)) + r")\b"
    excluded = [*handlers, "const", "final"]
    clauses = (
        lines.filter(
            (pl.col("indent") == pl.col("guard_column")) & pl.col("lines").str.contains(opening)
        )
        .with_columns(
            pl.col("lines")
            .str.split(" as ")
            .list.first()
            .str.extract_all(r"[A-Za-z_][A-Za-z0-9_]*")
            .alias("stated")
        )
        .with_columns(
            pl.when(
                pl.col("lines").str.strip_chars_end().str.ends_with(":")
                | (pl.col("stated").list.len() == 1)
            )
            .then(pl.col("stated"))
            .otherwise(pl.col("stated").list.slice(0, pl.col("stated").list.len() - 1))
            .list.eval(pl.element().filter(~pl.element().is_in(excluded)))
            .alias("caught")
        )
        .select("fact_id", "guard_ordinal", "offset", "caught")
    )
    return guards, clauses


def _thrown_inside_guards(
    relations: SyntaxTable,
    *,
    nodes: pl.LazyFrame,
    guards: pl.LazyFrame,
    clauses: pl.LazyFrame,
) -> pl.LazyFrame:
    """Return errors raised directly inside each protected guard region."""
    first_handlers = clauses.group_by("fact_id", "guard_ordinal", maintain_order=True).agg(
        pl.col("offset").min().alias("handler_offset")
    )
    protected = (
        relations.children.select(
            "fact_id",
            pl.col("parent_ordinal").alias("guard_ordinal"),
            "child_ordinal",
        )
        .join(first_handlers, on=["fact_id", "guard_ordinal"], how="inner")
        .join(
            guards.select("fact_id", "guard_ordinal", "guard_start_line"),
            on=["fact_id", "guard_ordinal"],
            how="inner",
        )
        .join(
            nodes.select(
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                pl.col("kind").alias("child_kind"),
                pl.col("start_line").alias("child_start_line"),
                pl.col("subtree_end").alias("child_end"),
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .filter(
            ~pl.col("child_kind").is_in(["callable", "type"])
            & (pl.col("child_start_line") < pl.col("guard_start_line") + pl.col("handler_offset"))
        )
    )
    raises = nodes.filter(pl.col("kind") == "raise").select(
        "fact_id",
        pl.col("ordinal").alias("raise_ordinal"),
        pl.col("subtree_end").alias("raise_end"),
    )
    candidates = protected.join(raises, on="fact_id", how="inner").filter(
        (pl.col("raise_ordinal") >= pl.col("child_ordinal"))
        & (pl.col("raise_ordinal") < pl.col("child_end"))
    )
    blockers = nodes.filter(pl.col("kind").is_in(["callable", "type"])).select(
        "fact_id",
        pl.col("ordinal").alias("blocker_ordinal"),
        pl.col("subtree_end").alias("blocker_end"),
    )
    blocked = (
        candidates.join(blockers, on="fact_id", how="inner")
        .filter(
            (pl.col("blocker_ordinal") >= pl.col("child_ordinal"))
            & (pl.col("blocker_ordinal") < pl.col("child_end"))
            & (pl.col("blocker_ordinal") <= pl.col("raise_ordinal"))
            & (pl.col("raise_ordinal") < pl.col("blocker_end"))
        )
        .select("fact_id", "guard_ordinal", "raise_ordinal")
        .unique()
    )
    unblocked = candidates.join(
        blocked,
        on=["fact_id", "guard_ordinal", "raise_ordinal"],
        how="anti",
    )
    expressions = nodes.filter(pl.col("kind").is_in(["call", "name"])).select(
        "fact_id", "ordinal", pl.col("name").str.split(".").list.last().alias("thrown")
    )
    return (
        unblocked.join(expressions, on="fact_id", how="inner")
        .filter(
            (pl.col("ordinal") >= pl.col("raise_ordinal"))
            & (pl.col("ordinal") < pl.col("raise_end"))
        )
        .group_by("fact_id", "guard_ordinal", "raise_ordinal", maintain_order=True)
        .agg(pl.col("thrown").sort_by("ordinal").first())
        .filter(pl.col("thrown") != "")
        .select("fact_id", "guard_ordinal", "thrown")
        .unique()
    )


@rule("ALL-ERRO0004")
def raise_inside_guarded_region(
    subject: Table[SyntaxFact],
    *,
    handlers: tuple[str, ...] = ("except", "catch", "rescue"),
    catch_all: tuple[str, ...] = ("Exception", "BaseException", "Error", "Throwable"),
) -> RuleQuery[int]:
    """Count guards that catch a failure their own protected region threw.

    Definition
    ----------
    Read every guard one declaration states, take the error names its own protected region raises,
    and report the guard when one of its handler clauses would catch one of them. A clause catches
    it when it names that error, when it names a base error such as `Exception` or `Error`, or when
    it names no type at all the way a bare `except` and a JavaScript `catch (error)` do. A raise
    written there is a jump to a handler a few lines below, which is a goto wearing the clothes of
    error handling, and the reader has to hold the whole region in mind to work out where control
    lands.

    The handler pays for it twice. It now answers both the failures the protected calls throw and
    the ones the body threw at itself, so it cannot recover from one without pretending to recover
    from the other, and a real failure from a real call arrives looking exactly like the check the
    body performed on purpose. Moving the check into the function that owns it leaves the guard
    protecting only calls it does not control, which is the one thing a guard is good at.

    Evidence
    --------
    Each finding names the declaration and the guard whose own body raises. The value is the
    number of guards that catch what they threw.

    Exceptions
    ----------
    A raise no clause would catch leaves the guard entirely and is left alone, which is why the
    names are compared at all rather than any raise in the region being reported. Comparing them
    lexically is what a reader does too, and a clause that catches a subclass by a name the raise
    never states is missed rather than guessed at. A guard that states no handler is how a language
    spells cleanup that always runs, and since it catches nothing it is never judged. A raise
    inside a callable the region declares is the very shape this rule asks for, so it is not
    counted even though it is written inside the region. A guard nested inside another is judged on
    its own, and both are reported when both could catch what the inner body threw. Only a callable
    is judged, because a type reaches every guard it owns through the callable holding it and would
    otherwise report the same one twice. `handlers` names the words a language opens a handler
    clause with and `catch_all` names the base errors a clause catches everything through, so a
    project whose own root error is caught that widely adds it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           record = fetch(key)
           if record.expired:
               raise StaleRecord(key)
       except StaleRecord:
           record = rebuild(key)

    Good
    ~~~~
    .. code-block:: python

       def fresh(key):
           record = fetch(key)
           if record.expired:
               raise StaleRecord(key)
           return record

       try:
           record = fresh(key)
       except StaleRecord:
           record = rebuild(key)

    References
    ----------
    Generalizes Ruff TRY301 raise-within-try
    https://docs.astral.sh/ruff/rules/raise-within-try/
    Cites "tryceratops documentation", the linter this check came from
    https://github.com/guilatrova/tryceratops
    Cites "Clean Code", chapter 7, error handling
    Cites "Refactoring", extract function
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    guards, clauses = _guards_and_clauses(relations, nodes, handlers)
    thrown = _thrown_inside_guards(
        relations,
        nodes=nodes,
        guards=guards,
        clauses=clauses,
    )
    caught_guards = (
        clauses.join(thrown, on=["fact_id", "guard_ordinal"], how="inner")
        .filter(
            (pl.col("caught").list.len() == 0)
            | pl.col("caught").list.contains(pl.col("thrown"))
            | pl.col("caught").list.eval(pl.element().is_in(list(catch_all))).list.any()
        )
        .select("fact_id", "guard_ordinal")
        .unique()
    )
    reported = (
        caught_guards.join(thrown, on=["fact_id", "guard_ordinal"], how="inner")
        .group_by("fact_id", "guard_ordinal", maintain_order=True)
        .agg(pl.col("thrown").unique().sort())
        .join(
            guards.select(
                "fact_id",
                "guard_ordinal",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
            ),
            on=["fact_id", "guard_ordinal"],
            how="inner",
        )
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.when(pl.col("kind") == "callable")
        .then(pl.col("value").fill_null(0))
        .otherwise(0)
        .alias("value")
    )
    callable_reported = reported.join(
        facts.filter(pl.col("kind") == "callable").select("fact_id"),
        on="fact_id",
        how="inner",
    )
    findings = FindingQuery.build(
        callable_reported,
        pl.concat_str(
            pl.lit("guard catches `"),
            pl.col("thrown").list.join(", "),
            pl.lit("` raised inside its own protected region"),
        ),
        (("raise inside guarded region", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("guard_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
