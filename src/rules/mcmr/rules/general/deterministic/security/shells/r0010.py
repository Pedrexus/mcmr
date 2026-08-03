import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable


@rule("ALL-SECU0005")
def command_built_from_a_shell_string(
    subject: Table[SyntaxFact], *, also_through_a_shell: tuple[str, ...] = ()
) -> RuleQuery[int]:
    """Count the process launches that hand a command line to a shell.

    Definition
    ----------
    Report a spawn that runs through a shell rather than through an argument list. A shell reads
    the string it receives and treats a space, a quote, a backtick, and a statement separator as
    syntax, so any value that reaches that string can append a second command the caller never
    wrote. Handing the launcher a list keeps every argument separate no matter what it holds,
    which is why the list form is the repair rather than another round of escaping. One rule
    answers for `os.system`, `shell_exec`, `child_process.exec`, and a command asked for `sh -c`.

    A command line built from parts is one whose first argument combines values and states part of
    the command itself. The operator alone does not say what it joined, so a piece of the command
    has to be written down inside the expression. Without that, two flags combined with a bitwise
    or read as an assembled command line in every brace language.

    Evidence
    --------
    Each finding names the declaration, the launcher, and the line. The value is how many launches
    reach a shell. The launcher is read from the last segment of the callee, so `System.out` and
    `os.system` stay apart.

    Exceptions
    ----------
    A launcher that says it does not want a shell, such as one written with `shell=False`, is left
    alone, and so is one handed an argument list, because a list is the shape this rule asks for.
    A launcher handed one constant command line has nothing an attacker can reach, so only a shell
    asked for by name and a command line built from parts are reported. An argument combining two
    values that names no part of a command, the way `exec_tag::sync | exec_tag::timer` does, is
    not a command line and is left alone. A project that wraps its own name around a shell names
    that wrapper through `also_through_a_shell`.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       subprocess.run(f"git checkout {ref}", shell=True)
       os.popen("git checkout " + ref)

    Good
    ~~~~
    .. code-block:: python

       subprocess.run(["git", "checkout", ref])

    .. code-block:: cpp

       state.exec(nvbench::exec_tag::sync | nvbench::exec_tag::timer, run);

    References
    ----------
    Generalizes Ruff S602 subprocess-popen-with-shell-equals-true
    https://docs.astral.sh/ruff/rules/subprocess-popen-with-shell-equals-true/
    Generalizes Ruff S604 call-with-shell-equals-true
    https://docs.astral.sh/ruff/rules/call-with-shell-equals-true/
    Generalizes Ruff S605 start-process-with-a-shell
    https://docs.astral.sh/ruff/rules/start-process-with-a-shell/
    Cites "Common Weakness Enumeration", CWE-78, improper neutralization in an OS command
    https://cwe.mitre.org/data/definitions/78.html
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    children = relations.children
    calls = relations.with_text(nodes.filter(pl.col("kind") == "call")).select(
        "fact_id",
        pl.col("ordinal").alias("call_ordinal"),
        pl.col("name").alias("call_name"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("name").str.to_lowercase().str.replace_all("::", ".").alias("callee"),
        pl.col("text").str.replace_all(" ", "").str.to_lowercase().alias("written"),
    )
    first_arguments = (
        children.filter(pl.col("child_order") == 1)
        .select(
            "fact_id",
            pl.col("parent_ordinal").alias("call_ordinal"),
            pl.col("child_ordinal").alias("argument_ordinal"),
        )
        .join(
            nodes.select(
                "fact_id",
                pl.col("ordinal").alias("argument_ordinal"),
                pl.col("kind").alias("argument_kind"),
                pl.col("subtree_end").alias("argument_end"),
            ),
            on=["fact_id", "argument_ordinal"],
            how="inner",
        )
    )
    text_descendants = nodes.filter(pl.col("kind") == "text").select(
        "fact_id", pl.col("ordinal").alias("text_ordinal")
    )
    built = (
        first_arguments.filter(pl.col("argument_kind") == "operation")
        .join(text_descendants, on="fact_id", how="inner")
        .filter(
            (pl.col("text_ordinal") >= pl.col("argument_ordinal"))
            & (pl.col("text_ordinal") < pl.col("argument_end"))
        )
        .select("fact_id", "call_ordinal")
        .unique(maintain_order=True)
        .with_columns(pl.lit(True).alias("built_from_parts"))
    )
    shell_only = [
        "system",
        "shell_exec",
        "passthru",
        "getoutput",
        "getstatusoutput",
        *also_through_a_shell,
    ]
    launchers = [
        "child_process.exec",
        "child_process.execsync",
        "child_process.spawn",
        "child_process.spawnsync",
        "os.popen",
        "runtime.exec",
        "subprocess.call",
        "subprocess.popen",
        "subprocess.run",
    ]
    asks = "shell=true|shell:true|usesshell|/bin/sh|/bin/bash|cmd\\.exe"
    reported = (
        calls.join(built, on=["fact_id", "call_ordinal"], how="left")
        .with_columns(pl.col("callee").str.split(".").list.last().alias("launched"))
        .filter(
            pl.col("launched").is_in(shell_only)
            | (
                pl.col("callee").is_in(launchers)
                & (
                    pl.col("built_from_parts").fill_null(False)
                    | pl.col("written").str.contains(asks)
                )
                & ~pl.col("written").str.contains("shell=false", literal=True)
            )
        )
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.lit("`"),
            pl.col("call_name"),
            pl.lit("` launches a command assembled as a shell string"),
        ),
        (("command built from a shell string", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("call_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
