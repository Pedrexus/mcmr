import re

from ..... import rule
from .....facts import SourceSpan, SyntaxFact, SyntaxNode
from .....models import Count

# How every language writes the clause it takes when the condition was false. A dedented `else` is
# the Python spelling and `} else {` is the one C, C++, Rust, and TypeScript share, so one pattern
# finds the clause in all of them without a rule learning any syntax.
_ALTERNATIVE = re.compile(r"\}?\s*(?:else|elif|elsif)\b")

# The first word of a statement, with the trailing bang a Rust macro carries, because `panic!` and
# `return` leave a block the same way and only the spelling differs.
_LEADING_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*!?")


def alternative_line(branch: SyntaxNode, span: SourceSpan) -> int:
    """Return the line where one branch opens the clause it takes when its condition was false.

    Only a clause written at the branch's own indentation counts, so a nested branch keeps its own
    else and the branch around it is never blamed for it. Zero means this branch opens none.
    """
    for offset, line in enumerate(branch.text.splitlines()):
        indent = len(line) - len(line.lstrip())
        if offset and indent == span.start_column and _ALTERNATIVE.match(line.strip()):
            return span.start_line + offset
    return 0


def closing_statement(branch: SyntaxNode, span: SourceSpan, at: int) -> str:
    """Return the last statement one branch runs before the line its alternative opens on.

    Structure answers this wherever a frontend states the statements a branch holds. A frontend
    that stops at the branch itself, or a tree the depth bound cut, leaves only the source, so the
    line above the alternative is read instead and counts only where it sits at the indentation the
    block opened with. That keeps a jump buried inside a nested body from being read as the one the
    block ends on.
    """
    stated = [
        (child.span.end_line, order, child.text.lstrip())
        for order, child in enumerate(branch.children)
        if child.span is not None and child.span.end_line < at
    ]
    if stated:
        return max(stated)[2]
    held = branch.text.splitlines()[1 : at - span.start_line]
    if not held:
        return ""
    opened = len(held[0]) - len(held[0].lstrip())
    return [line for line in held if len(line) - len(line.lstrip()) == opened][-1].lstrip()


def alternative_is_superfluous(branch: SyntaxNode, jumps: tuple[str, ...]) -> bool:
    """Whether one branch opens an alternative the statement above it already made unnecessary."""
    span = branch.span
    if span is None:
        return False
    at = alternative_line(branch, span)
    word = _LEADING_WORD.match(closing_statement(branch, span, at)) if at else None
    return word is not None and word.group() in jumps


@rule
def superfluous_else_after_jump(
    subject: SyntaxFact,
    *,
    jumps: tuple[str, ...] = ("return", "raise", "throw", "break", "continue", "panic!"),
) -> Count:
    """Count else clauses a jump in the block above them already made unnecessary.

    Definition
    ----------
    Report a branch whose last statement before the alternative leaves the block for good, through
    a return, a raise, a throw, a break, or a continue. Once that statement runs nothing else in
    the block runs, so the else adds no information a reader did not already have. What it does add
    is a level of indentation, and every level costs the reader one more condition to hold in mind
    while reading the rest of the work.

    The alternative is read at the branch's own indentation, which is `else` in Python and
    `} else {` in C, C++, Rust, and TypeScript, and the jump is read from the first word of the
    statement before it. Both readings are language neutral, so one rule answers for every frontend
    that fills a tree, and a frontend that states no statements inside a branch still gets an
    answer from the source the branch carries.

    Evidence
    --------
    Each finding names the declaration, the branch, and the line its alternative opens on. The
    value is the number of alternatives a jump already made unnecessary.

    Exceptions
    ----------
    A branch whose first block ends in ordinary work keeps its else, because there the else is the
    only thing saying the two blocks exclude each other. An else belonging to a nested branch is
    charged to that branch and never to the one holding it, which is what reading the indentation
    buys. A language whose block yields a value instead of jumping, such as a Rust `if` written as
    an expression, states no keyword to find and is left alone. A statement that closes its block
    on a brace or a bare continuation line, rather than on the word that jumps, is left alone too,
    which under-reports and never over-reports. A branch carrying no span at all is not judged,
    since nothing then locates the alternative.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       if not values:
           return 0
       else:
           return sum(values)

    Good
    ~~~~
    .. code-block:: python

       if not values:
           return 0
       return sum(values)

    The same shape in Rust is `if values.is_empty() { return 0; } else { ... }`, and the same
    repair drops the `else` and dedents everything it held.

    References
    ----------
    Generalizes Ruff RET505 superfluous-else-return
    Generalizes Ruff RET506 superfluous-else-raise
    Generalizes Ruff RET507 superfluous-else-continue
    Generalizes Ruff RET508 superfluous-else-break
    Cites Pylint R1705 no-else-return
    https://pylint.readthedocs.io/en/latest/user_guide/messages/refactor/no-else-return.html
    Cites "Go Code Review Comments", indent error flow
    https://go.dev/wiki/CodeReviewComments#indent-error-flow
    """
    if subject.tree is None:
        return 0
    return sum(
        alternative_is_superfluous(branch, jumps) for branch in subject.tree.of_kind("branch")
    )
