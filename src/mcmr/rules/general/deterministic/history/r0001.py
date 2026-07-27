from ..... import rule
from .....facts import RepositoryHistoryFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def large_file_the_team_keeps_reopening(
    subject: RepositoryHistoryFact,
    *,
    minimum_lines: int = 400,
    busy_share: float = 0.5,
    stale_days: int = 180,
) -> CountReport:
    """Count long files this repository keeps changing anyway.

    Definition
    ----------
    Report a file longer than `minimum_lines` whose change count reaches `busy_share` of the
    busiest file in the window and whose last change is no older than `stale_days`. Size alone
    names a file that is hard to read, and plenty of long files are read once a year and cost
    nobody anything. Size beside change frequency names one the team is paying for over and over,
    which is a different and far more urgent thing, and only the history knows the second half.

    Every threshold is relative or bounded on purpose. The busiest file sets the bar, so a quiet
    repository is not judged against a busy one, and a day count is read against the newest commit
    in the window rather than against the clock, so two runs over the same history agree.

    Evidence
    --------
    Each finding names the file, how long it is, how many commits touched it against the busiest
    file in the repository, and how many days ago that stopped. The repair is a choice, since a
    file everybody reopens is sometimes the one place a decision belongs. The value is the number
    of files scoring on all three.

    Exceptions
    ----------
    A file that stopped changing has already been paid for and is left alone, which is what
    `stale_days` buys. A generated file, a vendored dependency, and a lock file are long and busy
    without anybody reading them, so a project that keeps them in the tree excludes them rather
    than tuning the thresholds around them. A file the log holds but the tree no longer does reads
    as no lines at all and is never reported.

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
    busiest = max((record.commit_count for record in subject.files), default=0)
    if not busiest:
        return Reported(value=0)
    reopened = [
        record
        for record in subject.files
        if record.line_count >= minimum_lines
        and record.commit_count >= busiest * busy_share
        and record.days_since_last_change <= stale_days
    ]
    return Reported(
        value=len(reopened),
        findings=tuple(
            Finding(
                message=(
                    f"`{record.path}` runs {counted(record.line_count, 'line')} and took "
                    f"{counted(record.commit_count, 'commit')} against the {busiest} the busiest "
                    f"file took, the last of them "
                    f"{counted(record.days_since_last_change, 'day')} ago"
                ),
                span=SourceSpan(path=record.path),
                measurements=(
                    Measurement(name="lines", value=record.line_count),
                    Measurement(name="commits", value=record.commit_count),
                    Measurement(name="commits the busiest file took", value=busiest),
                    Measurement(
                        name="days since the last one", value=record.days_since_last_change
                    ),
                ),
                repair=Choice(
                    question=f"find out what keeps bringing people back to `{record.path}`",
                    options=(
                        "split off whatever changes on its own schedule",
                        "leave it where the file is the one place a decision belongs",
                    ),
                ),
            )
            for record in reopened
        ),
    )
