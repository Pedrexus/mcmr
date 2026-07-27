from ..... import rule
from .....facts import FunctionFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def function_implementation_lines(
    subject: FunctionFact,
) -> CountReport:
    """Measure how many executable lines one callable body holds.

    Definition
    ----------
    Take one function, method, or nested function, drop its signature, decorators, docstring, blank
    lines, and comment-only lines, and count the physical lines that remain from the first
    executable statement through the last. What is left is the work the body actually does, which
    is the length a reader has to follow.

    Documentation is deliberately not counted. A well-documented function would otherwise measure
    worse than an undocumented one, which would make the measurement argue against the thing it is
    supposed to encourage. The number is the measurement, and a project policy owns the ceiling.

    Evidence
    --------
    The finding names the callable, its exact source span, its implementation line count, how
    many statements sit directly in its body, and how many places the body branches. It states one
    finding for every callable rather than only for a long one, because the measurement is the
    whole answer here and a reader asking why a number is what it is has to be able to see it. The
    repair is a choice, since a body that is one cohesive algorithm is long for a reason. The value
    is the implementation line count.

    Exceptions
    ----------
    A generated, vendored, declarative, or framework-constrained body is long for a reason nobody
    in this repository can change, so provider selection is where those are excluded. A policy is a
    ceiling on badness rather than a claim that three-line functions are ideal, since splitting a
    cohesive body to satisfy a number produces helpers nobody can name. Ruff `PLR0915` counts
    statements rather than lines and reads as a complementary signal.

    Examples
    --------
    A function with a twelve-line docstring and twenty executable lines returns `20` rather than
    `32`. A body of thirty-one executable lines returns `31`, and a six-line cohesive body returns
    `6`. The configured policy, not this measurement, decides whether any of those values fails.

    References
    ----------
    Cites "Clean Code", chapter 3, Functions
    Cites "A Philosophy of Software Design", chapters 4 and 5
    Generalizes Ruff PLR0915 too-many-statements
    https://docs.astral.sh/ruff/rules/too-many-statements/
    """
    return Reported(
        value=subject.implementation_lines,
        findings=(
            Finding(
                message=(
                    f"`{subject.name}` runs "
                    f"{counted(subject.implementation_lines, 'line')} of implementation over "
                    f"{counted(subject.direct_statement_count, 'statement')} of its own"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="implementation lines", value=subject.implementation_lines),
                    Measurement(
                        name="statements in the body", value=subject.direct_statement_count
                    ),
                    Measurement(name="places it branches", value=len(subject.control_increments)),
                ),
                repair=Choice(
                    question=f"take a step out of `{subject.name}` and give it a name",
                    options=(
                        "extract the sections the body already separates",
                        "accept the length where the body is one cohesive algorithm",
                    ),
                ),
            ),
        ),
    )
