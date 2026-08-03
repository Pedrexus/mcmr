import re

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable

# One name as any language writes it, keeping the dots a member call needs and the bang a Rust
# macro carries, so `console.log` and `println!` arrive whole rather than in pieces.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*!?")


@rule("ALL-CONT0003")
def debug_artifact_left_behind(
    subject: Table[SyntaxFact],
    *,
    artifacts: tuple[str, ...] = (
        "print",
        "printf",
        "println!",
        "eprintln!",
        "dbg!",
        "console.log",
        "console.debug",
        "breakpoint",
        "debugger",
        "pdb.set_trace",
        "set_trace",
    ),
    exempt_segments: tuple[str, ...] = (
        "test",
        "tests",
        "cli",
        "main",
        "bin",
        "script",
        "scripts",
        "example",
        "examples",
    ),
) -> RuleQuery[int]:
    """Count console prints and debugger breakpoints left behind in ordinary code.

    Definition
    ----------
    Report a call or a statement naming a debug artifact inside a declaration that is neither a
    test nor a command line entry point. `print` in Python, `println!` and `dbg!` in Rust,
    `console.log` in TypeScript, and `printf` in C are the same artifact under five spellings, and
    so are `breakpoint`, `debugger`, and `set_trace`.

    The cost is real in both directions. A print writes to a stream nobody configured, so it cannot
    be filtered, routed, or turned off the way a logger can, and it follows the code into
    production where it slows a hot path and can leak whatever the developer was inspecting. A
    breakpoint is worse, since it stops a program that has no terminal attached and hangs it.

    Evidence
    --------
    Each finding names the declaration, the artifact, and the line. The value is the number of
    artifacts left behind.

    Exceptions
    ----------
    A file whose path holds a segment such as `tests`, `cli`, `bin`, or `main` is where writing to
    the console is the job, so nothing there is reported. Path segments are read whole, which keeps
    a module named `bindings` out of the `bin` exemption. A logger call is never an artifact, since
    a project that configured one already decided where its output goes. A name a frontend resolved
    is trusted as it stands, and only a bare macro or keyword falls back to reading text, where a
    matching word inside a string or a comment on the same line can be read as a call.
    `exempt_segments` is that list of path segments and `artifacts` is the list of debug names, so
    a project with its own console wrapper or its own script directory states them rather than
    living with the defaults.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def charge(order):
           print(order.card)
           breakpoint()
           return gateway.charge(order)

    Good
    ~~~~
    .. code-block:: python

       def charge(order):
           logger.debug("charging %s", order.id)
           return gateway.charge(order)

    References
    ----------
    Generalizes Ruff T201 print
    Generalizes Ruff T100 debugger
    Generalizes Clippy dbg_macro
    Generalizes Clippy print_stdout
    https://rust-lang.github.io/rust-clippy/master/index.html#dbg_macro
    Generalizes ESLint no-console
    Generalizes ESLint no-debugger
    https://eslint.org/docs/latest/rules/no-console
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    parents = (
        relations.children.select("fact_id", pl.col("parent_ordinal").alias("ordinal"))
        .unique()
        .with_columns(pl.lit(True).alias("has_children"))
    )
    candidates = nodes.filter(pl.col("kind").is_in(["call", "effect", "expression"])).join(
        parents, on=["fact_id", "ordinal"], how="left"
    )
    named = candidates.filter(pl.col("name") != "").select(
        "fact_id",
        "ordinal",
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("name").alias("display"),
        pl.col("name").is_in(list(artifacts)).cast(pl.UInt64).alias("amount"),
    )
    unnamed = relations.with_text(
        candidates.filter((pl.col("name") == "") & ~pl.col("has_children").fill_null(False))
    ).select(
        "fact_id",
        "ordinal",
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("text").str.strip_chars().alias("display"),
        (
            pl.col("text")
            .str.extract_all(_WORD.pattern)
            .list.eval(pl.element().is_in(list(artifacts)).cast(pl.UInt64))
            .list.sum()
        ).alias("amount"),
    )
    exempt = (
        "(?:^|[\\\\/._-])(?:" + "|".join(map(re.escape, exempt_segments)) + ")(?:$|[\\\\/._-])"
    )
    reported = pl.concat([named, unnamed], how="vertical").filter(
        (pl.col("amount") > 0) & ~pl.col("path").str.to_lowercase().str.contains(exempt)
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.col("amount").sum().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.lit("`"),
            pl.col("display"),
            pl.lit("` leaves "),
            pl.col("amount"),
            pl.lit(" debug artifact behind"),
        ),
        (("debug artifact left behind", pl.col("amount"), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
    )
    return RuleQuery.integer(values, pl.col("value"), findings=findings)
