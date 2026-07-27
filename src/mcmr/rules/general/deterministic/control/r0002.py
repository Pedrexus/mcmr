import re

from ..... import rule
from .....facts import SyntaxFact, SyntaxNode
from .....models import Count

# The operators that only ever read their operands. Everything else an operation can hold is
# something a library overloads to do real work, such as the `&` that runs a command and the `>>`
# that wires one task to the next, so an operation is only inert when it states one of these.
_INERT_OPERATOR = re.compile(r"[=!<>]=|\bis\b|\bin\b|\bnot\b")


def whole_statement_value(statement: SyntaxNode) -> SyntaxNode | None:
    """Return the expression one statement is made of, when the tree states it as one node.

    A frontend that wraps the expression inside the statement states both, and the value is the
    child covering exactly the statement's own source. A frontend that instead marks the expression
    itself as the statement has overwritten the kind that carried the answer, so what sits beneath
    it are the operands rather than the content, and reading one would judge a call argument as if
    it were the whole line.
    """
    return next(
        (child for child in statement.children if child.span == statement.span),
        None,
    )


def discards_its_value(value: SyntaxNode, inert_kinds: tuple[str, ...]) -> bool:
    """Whether one expression standing alone as a statement can only produce a value.

    Every kind but an operation answers this from the kind alone. An operation has to be read
    further, because a comparison computes a Boolean and stops while an overloaded operator is how
    several languages spell a command.
    """
    if value.kind not in inert_kinds:
        return False
    return value.kind != "operation" or _INERT_OPERATOR.search(value.text) is not None


@rule
def statement_without_effect(
    subject: SyntaxFact,
    *,
    inert_kinds: tuple[str, ...] = ("name", "member", "literal", "collection", "operation"),
) -> Count:
    """Count statements that compute a value and then throw it away.

    Definition
    ----------
    Report a statement whose whole content is one expression that can only produce a value, such as
    a bare name, a comparison, a literal, or a collection. Nothing happens when the line runs, so
    it is either a mistake or a line nobody needs to read. The mistake is the common case, and it
    is usually an assertion that lost its `assert`, an assignment that lost its target, or a call
    that lost its parentheses, all of which look like working code and quietly test nothing.

    What counts is the statement's whole content, which is the one node covering exactly the source
    the statement covers. Everything else beneath a statement is an operand, and an operand says
    nothing about whether the line did any work, since the `1` inside `exit(1)` is a literal in a
    statement that ends the program. Reading the widest node rather than any node underneath is
    what keeps the two apart in every language. An operation is then the one kind read further,
    since `==` compares and stops while `&`, `|`, and `>>` are how several libraries spell a
    command that runs.

    Evidence
    --------
    Each finding names the declaration, the line, and the kind of the value thrown away. The value
    is the number of statements without an effect.

    Exceptions
    ----------
    A call, an await, and a string are never counted. A call may do all its work through a side
    effect, an await always can, and a string alone is a docstring or a comment in the languages
    that allow one. An index is not counted either, because reading through an operator a type
    defines is how several libraries probe for something and how a mapping raises when it is
    missing. An operation reaching its operands through anything but a comparison, a membership
    test, or a negation is left alone, which keeps a plumbum `command & FG` and an Airflow `first
    >> second` out of the findings and costs only the rare bare `a < b`. A statement the tree cut
    at its depth bound arrives with nothing beneath it and is not judged. Neither is a statement
    whose expression the frontend marked in place, replacing the kind of the value with the mark,
    because the fact then no longer states what the line computed and any answer would be read off
    an operand, so a frontend in that shape reports nothing here rather than guessing.
    `inert_kinds` names the node kinds that can only produce a value, which is what a project
    extends when its language states one this list has not met.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def check(order):
           order.total == 0
           order.items

    Good
    ~~~~
    .. code-block:: python

       def check(order):
           assert order.total == 0
           return order.items

    References
    ----------
    Generalizes Ruff B015 useless-comparison
    Generalizes Ruff B018 useless-expression
    Generalizes Clippy no_effect
    https://rust-lang.github.io/rust-clippy/master/index.html#no_effect
    Generalizes ESLint no-unused-expressions
    https://eslint.org/docs/latest/rules/no-unused-expressions
    """
    if subject.tree is None:
        return 0
    return sum(
        discards_its_value(value, inert_kinds)
        for statement in subject.tree.of_kind("effect")
        if (value := whole_statement_value(statement)) is not None
    )
