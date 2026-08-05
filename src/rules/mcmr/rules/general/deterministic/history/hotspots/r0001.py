import polars as pl
from pydantic import NonNegativeInt, PositiveInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import Ratio, RepositoryHistoryFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import HistoryRelations, Table
from ..messages import counted_text


@rule("ALL-HIST0001", policy=Numeric())
def large_file_the_team_keeps_reopening(
    subject: Table[RepositoryHistoryFact],
    *,
    minimum_lines: NonNegativeInt = 400,
    minimum_commits: PositiveInt = 2,
    busy_share: Ratio = 0.5,
    stale_days: NonNegativeInt = 180,
) -> CountQuery:
    """Count long files this repository keeps changing anyway.

    Definition
    ----------
    Report a file longer than `minimum_lines` with at least `minimum_commits` changes, whose change
    count reaches `busy_share` of the busiest file in the window, and whose last change is no older
    than `stale_days`. Size alone names a file that is hard to read, and plenty of long files are
    read once a year and cost nobody anything. Size beside repeated change names one the team is
    paying for over and over, which is a different and far more urgent thing, and only the history
    knows the second half.

    Every threshold is relative or bounded on purpose. The busiest file sets the bar, so a quiet
    repository is not judged against a busy one, and a day count is read against the newest commit
    in the window rather than against the clock, so two runs over the same history agree.

    Being relative is also why this is a measurement rather than a defect. The busiest file always
    reaches its own share, so any repository whose busiest file is long and current reports at
    least one however carefully it was written, and a ceiling of zero would only be restating the
    module size rules under a second name. What the count is worth is a judgment about ownership
    that the history cannot make, so the rule publishes the number and a project states the
    ceiling it wants held.

    Evidence
    --------
    Each finding names the file, how long it is, how many commits touched it against the busiest
    file in the repository, and how many days ago that stopped. The repair is a choice, since a
    file everybody reopens is sometimes the one place a decision belongs. The value is the number
    of files scoring on all three.

    Exceptions
    ----------
    A file seen in fewer than `minimum_commits` changes has not been reopened, and a file that
    stopped changing has already been paid for and is left alone, which is what `stale_days` buys.
    A generated file, a vendored dependency, and a lock file are long and busy without anybody
    reading them, so a project that keeps them in the tree excludes them rather than tuning the
    thresholds around them. A file the log holds but the tree no longer does reads as no lines at
    all and is never reported.

    Nothing here fails on its own. A project that wants a churn budget states a numeric policy
    against this rule under `tool.mcmr`, and the count is then judged against that ceiling exactly
    as a rule-owned one would be, which is how a young repository and a decade-old one can hold
    themselves to different numbers without either editing the rule.

    Examples
    --------
    Bad
    ~~~
    A 2,255 line `cli.py` that 51 commits touched, more than any other file, most recently last
    week. Every feature lands in it, so every reader has to hold all of it.

    Good
    ~~~~
    A 3,000 line generated parser table that one commit created two years ago. It is longer than
    anything else and nobody has had to read it since, so nothing is owed here.

    References
    ----------
    Cites "Your Code as a Crime Scene", chapter 4, hotspots as complexity beside churn
    Cites "Software Design X-Rays", chapter 2, prioritizing technical debt
    Cites "Use of Relative Code Churn Measures to Predict System Defect Density", ICSE 2005
    https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/
    """
    relations = HistoryRelations(subject)
    files = relations.files()
    busiest = files.group_by("fact_id", maintain_order=True).agg(
        pl.col("commit_count").max().alias("busiest")
    )
    reopened = files.join(busiest, on="fact_id", how="inner").filter(
        (pl.col("line_count") >= minimum_lines)
        & (pl.col("commit_count") >= minimum_commits)
        & (pl.col("commit_count") >= pl.col("busiest") * busy_share)
        & (pl.col("days_since_last_change") <= stale_days)
    )
    frame = relations.counted(reopened)
    findings = FindingQuery.build(
        reopened,
        pl.concat_str(
            pl.lit("`"),
            pl.col("file_path"),
            pl.lit("` runs "),
            counted_text(pl.col("line_count"), "line"),
            pl.lit(" and took "),
            counted_text(pl.col("commit_count"), "commit"),
            pl.lit(" against the "),
            pl.col("busiest"),
            pl.lit(" the busiest file took, the last of them "),
            counted_text(pl.col("days_since_last_change"), "day"),
            pl.lit(" ago"),
        ),
        (
            ("lines", pl.col("line_count"), Unit.COUNT),
            ("commits", pl.col("commit_count"), Unit.COUNT),
            ("commits the busiest file took", pl.col("busiest"), Unit.COUNT),
            (
                "days since the last one",
                pl.col("days_since_last_change"),
                Unit.COUNT,
            ),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(
            pl.lit("find out what keeps bringing people back to `"),
            pl.col("file_path"),
            pl.lit("`"),
        ),
        options=(
            "split off whatever changes on its own schedule",
            "leave it where the file is the one place a decision belongs",
        ),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
