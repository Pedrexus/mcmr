from ..... import rule
from .....facts import CloneGroupFact
from .....models import Finding, Measurement, PercentageReport, Reported, Unit, counted


@rule
def duplicated_repository_share(
    subject: CloneGroupFact,
    *,
    minimum_line_count: int = 4,
) -> PercentageReport:
    """Measure how much of the repository exists only as a copy of this block.

    Definition
    ----------
    Divide the lines this group repeats by every line the kernel read, and state the result as a
    percentage. A group of three copies covering twelve lines repeats twenty-four of them, since
    one copy is the original and the other two are what a merge would remove. A group covering
    fewer than `minimum_line_count` lines measures zero, because a run that short is shape rather
    than a paste and counting it would inflate a number people act on.

    Symilar reports the same quantity for a whole run, as duplicated lines over total lines. This
    rule reports it one group at a time, which is what makes it actionable. A repository is never
    told to reduce duplication in general, it is told that one particular block accounts for a
    share of it that nobody meant to write.

    Evidence
    --------
    The finding names where the group was first stated, how many lines it repeats, and how many
    lines the whole tree holds, and the value is the share of the tree those repeated lines
    occupy. The denominator is every line of every file the kernel read, including blank ones,
    which is the same denominator Symilar divides by.

    Exceptions
    ----------
    A repository the kernel read nothing from measures zero rather than failing, since a share of
    nothing has no meaning. Generated and vendored trees are excluded before the kernel reads
    them, so a checked-in build directory never counts against the tree that wrote it. A copy that
    is deliberate, such as a test double that mirrors the shape it stands in for, still counts
    here, because this rule measures the tree rather than judging the intent behind it.

    Examples
    --------
    Bad
    ~~~
    One eighty-line reader pasted into three modules of a two-thousand-line repository repeats one
    hundred and sixty lines, so it returns `8.0` and every fix to it has to be made three times.

    Good
    ~~~~
    The same reader lives in one module the other three import. Nothing is repeated, so the group
    disappears and the share is `0.0`. A group covering three lines also returns `0.0`, because it
    sits under the default `minimum_line_count`.

    References
    ----------
    Generalizes Pylint R0801 duplicate-code
    Cites "Clean Code", chapter 17, on duplication as the primary enemy of design
    Cites "Working Effectively with Legacy Code", chapter 20, on extraction
    """
    if subject.line_count < minimum_line_count or not subject.repository_line_count:
        return Reported(value=0.0)
    share = subject.redundant_line_count / subject.repository_line_count * 100.0
    return Reported(
        value=share,
        findings=(
            Finding(
                message=(
                    f"{subject.redundant_line_count} of the "
                    f"{counted(subject.repository_line_count, 'line')} this tree holds repeat a "
                    f"block of {counted(subject.line_count, 'line')} that appears "
                    f"{counted(subject.copy_count, 'time')}"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="repeated lines", value=subject.redundant_line_count),
                    Measurement(name="lines in the tree", value=subject.repository_line_count),
                    Measurement(name="share of the tree", value=share, unit=Unit.PERCENTAGE),
                ),
            ),
        ),
    )
