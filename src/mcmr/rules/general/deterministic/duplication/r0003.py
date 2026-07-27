from ..... import rule
from .....facts import CloneGroupFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def pasted_block_copy_count(
    subject: CloneGroupFact,
    *,
    minimum_token_length: int = 60,
    minimum_line_count: int = 4,
) -> CountReport:
    """Count the copies of a block that exist only because it was pasted.

    Definition
    ----------
    Read one group of fragments the kernel matched on normalized tokens, where every identifier
    became a placeholder and every literal became a placeholder for its kind, so a copy is still a
    copy after its locals were renamed and its formatting was redone. Report the copies past the
    first when the repeated run reaches `minimum_token_length` normalized tokens and covers at
    least `minimum_line_count` lines. The value is what a reader would delete, since one of the
    copies is the one worth keeping.

    The kernel admits implementation blocks from forty normalized tokens so it can retain compact
    pasted bodies. This rule defaults to sixty before calling one a defect, while four lines is
    what Symilar asks for by default. Raising the token floor is the honest way to ask for fewer
    findings, because the cost of matching on shape is that short pieces of implementation can
    look alike without sharing knowledge.

    Evidence
    --------
    One finding is stated per copy past the first, each located at that copy and naming the lines
    the original covers, so the number of findings and the value are the same number read two
    ways. Each carries how many lines and how many tokens the block runs to, and the repair is a
    choice, because two blocks that look alike are not always the same idea.

    Exceptions
    ----------
    A run under either floor is not reported at all, because normalization deliberately throws
    away every name and every literal and short runs of shape are ordinary rather than copied. A
    group whose copies all sit inside a longer group is never built, so a long paste is one
    finding rather than one for each of the shorter readings inside it. Whether the copies should
    be merged is a judgment about shared knowledge that this rule does not make, and
    `ALL-DUPL2003` reads the very same fact to make it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def total_over(rows, limit):
           total = 0
           for row in rows:
               total = total + row.value if row.value > limit else total
           return total

       def sum_above(items, floor):
           carried = 0
           for item in items:
               carried = carried + item.value if item.value > floor else carried
           return carried

    Good
    ~~~~
    .. code-block:: python

       def total_over(rows, limit):
           return sum(row.value for row in rows if row.value > limit)

    References
    ----------
    Generalizes Pylint R0801 duplicate-code
    Cites "The Pragmatic Programmer", the DRY principle
    Cites "Refactoring", Extract Function
    https://refactoring.com/catalog/extractFunction.html
    """
    if subject.token_length < minimum_token_length or subject.line_count < minimum_line_count:
        return Reported(value=0)
    original, *copies = subject.fragments
    return Reported(
        value=subject.copy_count - 1,
        findings=tuple(
            Finding(
                message=(
                    f"this implementation spans {counted(copy.line_count, 'line')} and repeats "
                    f"the same {subject.token_length}-token normalized structure as "
                    f"`{original.path}` at lines {original.start_line} to {original.end_line}"
                ),
                span=SourceSpan(
                    path=copy.path, start_line=copy.start_line, end_line=copy.end_line
                ),
                measurements=(
                    Measurement(name="repeated lines", value=copy.line_count),
                    Measurement(name="tokens in the block", value=subject.token_length),
                    Measurement(name="copies of it in the tree", value=subject.copy_count),
                ),
                repair=Choice(
                    question="name this block once and call it from both places",
                    options=(
                        "extract it where the two copies mean the same thing",
                        "let them diverge where they only look alike",
                    ),
                ),
            )
            for copy in copies
        ),
    )
