import re

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable


def _guard_lines(
    relations: SyntaxTable, nodes: pl.LazyFrame, handlers: tuple[str, ...]
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Expand each guard into located source lines and its handler clauses."""
    guards = relations.with_text(nodes.filter(pl.col("kind") == "guard")).select(
        "fact_id",
        pl.col("ordinal").alias("guard_ordinal"),
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
            ).alias("indent"),
            pl.col("lines").str.strip_chars().alias("stripped"),
        )
    )
    opening = r"^[}\t ]*(?:" + "|".join(map(re.escape, handlers)) + r")\b"
    clauses = (
        lines.filter(pl.col("lines").str.contains(opening))
        .select(
            "fact_id",
            "guard_ordinal",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            pl.col("offset").alias("handler_offset"),
            pl.col("indent").alias("margin"),
            pl.col("lines").str.extract(r".*(?:\{|:)(.*)$", 1).fill_null("").alias("inline"),
        )
        .with_row_index("handler_id")
    )
    return lines, clauses


def _swallowed_handlers(
    *, lines: pl.LazyFrame, clauses: pl.LazyFrame, inert: tuple[str, ...]
) -> pl.LazyFrame:
    """Return handler groups whose statements contain no reaction."""
    boundaries = (
        clauses.join(lines, on=["fact_id", "guard_ordinal"], how="inner")
        .filter(
            (pl.col("offset") > pl.col("handler_offset"))
            & ~((pl.col("indent") > pl.col("margin")) | pl.col("stripped").is_in(["{", ""]))
        )
        .group_by("handler_id", maintain_order=True)
        .agg(pl.col("offset").min().alias("boundary"))
    )
    held = (
        clauses.join(boundaries, on="handler_id", how="left")
        .join(lines, on=["fact_id", "guard_ordinal"], how="inner")
        .filter(
            (pl.col("offset") > pl.col("handler_offset"))
            & (pl.col("boundary").is_null() | (pl.col("offset") < pl.col("boundary")))
        )
        .select("handler_id", pl.col("lines").alias("statement"))
    )
    statements = pl.concat(
        [clauses.select("handler_id", pl.col("inline").alias("statement")), held],
        how="vertical",
    ).with_columns(
        pl.col("statement")
        .str.split("#")
        .list.first()
        .str.split("//")
        .list.first()
        .str.strip_chars(" \t{};")
        .alias("cleaned")
    )
    return (
        clauses.join(
            statements.group_by("handler_id", maintain_order=True).agg(
                ((pl.col("cleaned") != "") & ~pl.col("cleaned").is_in(list(inert)))
                .any()
                .alias("has_reaction")
            ),
            on="handler_id",
            how="left",
        )
        .filter(~pl.col("has_reaction").fill_null(False))
        .group_by("fact_id", "guard_ordinal", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("amount"),
            pl.col("path").first(),
            pl.col("start_line").first(),
            pl.col("start_column").first(),
            pl.col("end_line").first(),
            pl.col("end_column").first(),
        )
    )


def _discarded_bindings(relations: SyntaxTable, nodes: pl.LazyFrame, discard: str) -> pl.LazyFrame:
    """Return throwaway bindings whose right side contains a call."""
    declarators = ["let", "const", "var", "val", "mut", discard]
    binding_words = (
        pl.col("text").str.split("=").list.first().str.extract_all(r"[A-Za-z_][A-Za-z0-9_]*")
    )
    return (
        relations.with_text(nodes.filter(pl.col("kind") == "binding"))
        .with_columns(binding_words.alias("words"))
        .filter(
            pl.col("words").list.contains(discard)
            & pl.col("words").list.eval(pl.element().is_in(declarators)).list.all()
        )
        .select(
            "fact_id",
            pl.col("ordinal").alias("binding_ordinal"),
            pl.col("subtree_end").alias("binding_end"),
            pl.col("text").str.strip_chars().alias("binding_text"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
        )
        .join(
            nodes.filter(pl.col("kind") == "call").select("fact_id", "ordinal"),
            on="fact_id",
            how="inner",
        )
        .filter(
            (pl.col("ordinal") >= pl.col("binding_ordinal"))
            & (pl.col("ordinal") < pl.col("binding_end"))
        )
        .select(
            "fact_id",
            "binding_ordinal",
            "binding_text",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
        )
        .unique()
    )


@rule("ALL-ERRO0001")
def swallowed_error(
    subject: Table[SyntaxFact],
    *,
    handlers: tuple[str, ...] = ("except", "catch", "rescue"),
    inert: tuple[str, ...] = ("pass", "continue", "..."),
    discard: str = "_",
    failures_as_values: tuple[str, ...] = ("rust", "go"),
) -> RuleQuery[int]:
    """Count failures a declaration catches and then answers with nothing.

    Definition
    ----------
    Read every guard one declaration states and report each handler clause whose body does no
    work. An empty body, a lone `pass`, a lone `continue`, and a lone ellipsis all say the same
    thing, which is that the failure was seen and then dropped, so `except ValueError` followed by
    `pass` in Python and an empty `catch {}` in TypeScript or C++ land here together. Where a
    language hands failures back as values rather than throwing them, the same discard is written
    as a binding to the throwaway name, and `let _ = fallible()` in Rust counts for that reason.

    A dropped failure costs far more than the failure itself. Everything after the guard runs on
    state the failed step never finished writing, so the program carries on and produces a wrong
    answer confidently, and the person reading the logs a week later sees a clean run instead of
    the one line that would have named the cause.

    Evidence
    --------
    Each finding names the declaration, the guard, and the handler that answers with nothing. The
    value is the number of failures the declaration throws away.

    Exceptions
    ----------
    A handler that logs, returns a fallback, retries, or raises anything at all has answered the
    failure and is left alone. A comment is not an answer, because the run still carries on as if
    nothing had gone wrong, so a handler holding only a comment is reported. A binding to the
    throwaway name counts only when it throws away the result of a call, since `_ = 3` discards no
    failure, and only where the language returns failures as values, because `_ = risky()` in
    Python or TypeScript drops a value while the exception carries on regardless. A pattern that
    binds other names beside the throwaway, such as `let Some((_, rest)) = split(path)`, is
    destructuring rather than a discard and keeps the part it kept. The inert words, the throwaway
    name, and the languages that return failures are all settings, since a project may spell its
    own no-op and a language MCMR has not met yet may spell either differently. Only a callable is
    judged, because a guard belongs to code that runs and a type reaches every guard it owns
    through the callable holding it, which would otherwise report the same one twice. `handlers`
    names the words a language opens a handler clause with and `failures_as_values` names the
    languages that return failures rather than throwing them, which is what decides whether a
    discard binding is read at all.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           deliver(message)
       except TimeoutError:
           pass

    Good
    ~~~~
    .. code-block:: python

       try:
           deliver(message)
       except TimeoutError:
           logger.warning("delivery timed out, queued for retry", extra=message.trace())
           queue.retry(message)

    References
    ----------
    Generalizes Ruff S110 try-except-pass
    https://docs.astral.sh/ruff/rules/try-except-pass/
    Generalizes Ruff S112 try-except-continue
    https://docs.astral.sh/ruff/rules/try-except-continue/
    Cites "Common Weakness Enumeration", CWE-390, detection of error condition without action
    https://cwe.mitre.org/data/definitions/390.html
    Generalizes Clippy let_underscore_must_use
    https://rust-lang.github.io/rust-clippy/master/index.html#let_underscore_must_use
    Cites "Effective Java", item 77, do not ignore exceptions
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    lines, clauses = _guard_lines(relations, nodes, handlers)
    swallowed = _swallowed_handlers(lines=lines, clauses=clauses, inert=inert)
    swallowed_counts = swallowed.group_by("fact_id", maintain_order=True).agg(
        pl.col("amount").sum().cast(pl.UInt64).alias("handler_value")
    )
    discarded_bindings = _discarded_bindings(relations, nodes, discard)
    binding_counts = discarded_bindings.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("binding_value")
    )
    values = (
        facts.join(swallowed_counts, on="fact_id", how="left")
        .join(binding_counts, on="fact_id", how="left")
        .with_columns(
            pl.when(pl.col("kind") != "callable")
            .then(0)
            .otherwise(
                pl.col("handler_value").fill_null(0)
                + pl.when(pl.col("language").is_in(list(failures_as_values)))
                .then(pl.col("binding_value").fill_null(0))
                .otherwise(0)
            )
            .alias("value")
        )
    )
    location = (
        pl.when(pl.col("end_line") > pl.col("start_line"))
        .then(
            pl.concat_str(
                pl.col("path"),
                pl.lit(":"),
                pl.col("start_line"),
                pl.lit("-"),
                pl.col("end_line"),
            )
        )
        .otherwise(pl.concat_str(pl.col("path"), pl.lit(":"), pl.col("start_line")))
    )
    guard_findings = swallowed.join(
        facts.filter(pl.col("kind") == "callable").select("fact_id"),
        on="fact_id",
        how="inner",
    ).select(
        "fact_id",
        pl.col("guard_ordinal").alias("finding_order"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "amount",
        pl.concat_str(
            pl.lit("guard at `"),
            location,
            pl.lit("` has "),
            pl.col("amount"),
            pl.lit(" handlers that answer a failure with nothing"),
        ).alias("message"),
    )
    binding_findings = discarded_bindings.join(
        facts.filter(
            (pl.col("kind") == "callable") & pl.col("language").is_in(list(failures_as_values))
        ).select("fact_id"),
        on="fact_id",
        how="inner",
    ).select(
        "fact_id",
        pl.col("binding_ordinal").alias("finding_order"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.lit(1, dtype=pl.UInt64).alias("amount"),
        pl.concat_str(
            pl.lit("`"),
            pl.col("binding_text"),
            pl.lit("` discards the result of a fallible call"),
        ).alias("message"),
    )
    reported = pl.concat([guard_findings, binding_findings], how="vertical")
    findings = FindingQuery.build(
        reported,
        pl.col("message"),
        (("swallowed error", pl.col("amount"), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
    )
    return RuleQuery.integer(values, pl.col("value"), findings=findings)
