import polars as pl

from ..... import rule
from .....facts import AutomationTaskFact
from .....query import FindingQuery, OccurrenceQuery, RuleQuery
from .....table import Table


@rule("ALL-LIFE0001")
def project_automation(
    subject: Table[AutomationTaskFact],
    *,
    required_tasks: tuple[str, ...] = ("setup", "lint", "typecheck", "test", "build"),
) -> OccurrenceQuery:
    """Detect repeatable project work missing a canonical task.

    Definition
    ----------
    Check that each configured lifecycle action resolves to exactly one command, that the command
    stays inside the checkout, and that it completes with nobody at the terminal. The value is true
    when any required action fails one of the three.

    A command stays inside the checkout when it operates this repository through the environment
    the manifest declares. It leaves when it runs somewhere else or as somebody else, when it
    installs into the machine or fetches from the network instead of using that environment, or
    when the program it runs is an absolute path or one under a person's home directory, because
    none of those is carried by a fresh clone. It completes unattended when nothing in it opens a
    session, which an interactive flag, an editor, a pager, and a debugger each do.

    Evidence
    --------
    Findings retain the capability, every command declared for it, and which of the three
    conditions failed. The value is true for a repository missing any required action.

    Exceptions
    ----------
    Deployment and destructive maintenance can remain approval-gated while still automated.
    `required_tasks` names the lifecycle actions a project expects to be automated, defaulting to
    setup, lint, typecheck, test, and build.

    Examples
    --------
    A repository whose `setup`, `lint`, `typecheck`, `test`, and `build` each resolve to one
    command that runs unattended inside the checkout returns `false`. Declaring `setup` as
    `sudo apt-get install libfoo` returns `true`, since the machine rather than the repository
    carries that. So does a `test` written as `pytest --pdb`, which stops for a person. Two
    different commands under one capability, one in the default table and one in an environment
    table, also return `true`, since neither is canonical.

    References
    ----------
    Cites "The Pragmatic Programmer", on automation
    Cites "Software Engineering at Google", build systems
    """
    relations = subject
    canonical = (
        relations.records("tasks")
        .filter(
            (pl.col("commands.length") == 1)
            & pl.col("is_repository_owned")
            & pl.col("is_noninteractive")
            & pl.col("capability").is_in(required_tasks)
        )
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("capability").n_unique().alias("canonical"))
    )
    facts = (
        relations.facts()
        .join(canonical, on="fact_id", how="left")
        .with_columns(pl.col("canonical").fill_null(0))
        .with_columns((pl.col("canonical") < len(set(required_tasks))).alias("value"))
    )
    return RuleQuery.boolean(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_boolean(
            facts,
            pl.col("value"),
            "project automation",
            evidence=pl.col("evidence"),
        ),
    )
