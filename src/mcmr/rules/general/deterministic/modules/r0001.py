from ..... import rule
from .....facts import ModuleFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def module_line_count(
    subject: ModuleFact,
) -> CountReport:
    """Measure how many physical lines one module holds.

    Definition
    ----------
    Count every physical line of this source file, including comments, docstrings, and blank lines.
    Length is what a reader pays before understanding anything, and counting the lines as written
    is the only count that matches what they scroll through.

    The measurement stops at the number. A separate policy compares it against a ceiling a project
    chose, such as four hundred lines, because a generated schema and a hand-written service
    tolerate very different lengths and only the project knows which one this is.

    Evidence
    --------
    The finding names the module, its exact physical line count, and how many classes and
    functions that length is spent on, which is what says whether a long module is one large
    subject or several small ones sharing a file. The repair is a choice, since splitting by line
    count alone produces fragments nobody can name. The value is the physical line count.

    Exceptions
    ----------
    A generated file, a vendored dependency, a schema-heavy module, and a migration are long for
    reasons nobody is going to fix, so a project excludes them or judges them under a separate
    policy. Splitting a long module into arbitrary fragments, inheritance layers, or forwarding
    files makes the count smaller and the codebase worse, so a repair is worth checking against
    cohesion. Pylint `C0302` measures the same thing, so a project already running it with the same
    ceiling should disable one of the two.

    Examples
    --------
    A four-hundred-and-one-line module returns `401` and a three-hundred-and-fifty-line one returns
    `350`. Neither value is a failure by itself, since the configured policy is what decides which
    lengths this project accepts.

    References
    ----------
    Cites Pylint C0302 too-many-lines
    https://pylint.readthedocs.io/en/latest/user_guide/messages/convention/too-many-lines.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    return Reported(
        value=subject.physical_line_count,
        findings=(
            Finding(
                message=(
                    f"`{subject.span.path}` runs "
                    f"{counted(subject.physical_line_count, 'line')} holding "
                    f"{counted(subject.class_count, 'class', 'classes')} and "
                    f"{counted(subject.function_count, 'function')}"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="physical lines", value=subject.physical_line_count),
                    Measurement(name="classes", value=subject.class_count),
                    Measurement(name="functions", value=subject.function_count),
                ),
                repair=Choice(
                    question=f"split `{subject.span.path}` along a seam a reader can name",
                    options=(
                        "move one whole subject into its own module",
                        "accept the length where the module is one subject",
                    ),
                ),
            ),
        ),
    )
