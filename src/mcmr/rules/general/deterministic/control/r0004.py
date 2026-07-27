from ..... import rule
from .....facts import SyntaxFact, SyntaxNode


def continues(child: SyntaxNode, holder: SyntaxNode) -> bool:
    """Whether one construct carries on the one holding it instead of nesting inside it.

    A chained alternative closes exactly where the construct it continues closes and is never
    written deeper than it. That is how `elif`, `else if`, and `} else if {` all read, as one more
    arm of the same decision rather than one more level of indentation, and a language that models
    the chain as a branch inside a branch would otherwise be charged for every arm.
    """
    return (
        child.span is not None
        and holder.span is not None
        and (child.span.end_line, child.span.end_column)
        == (holder.span.end_line, holder.span.end_column)
        and child.span.start_column <= holder.span.start_column
    )


def nesting(node: SyntaxNode, body_kinds: tuple[str, ...]) -> int:
    """Return the longest chain of nested bodies at or beneath one node.

    `SyntaxNode.depth` measures the whole tree, where an argument inside a call inside a comparison
    counts three levels that cost a reader nothing. Only a construct opening a body of its own is
    counted here, and only where it opens that body deeper than the construct holding it, which is
    the nesting a reader actually pays for.
    """
    deepest = max(
        (
            nesting(child, body_kinds) - (child.kind in body_kinds and continues(child, node))
            for child in node.children
        ),
        default=0,
    )
    return deepest + (node.kind in body_kinds)


@rule
def deeply_nested_body(
    subject: SyntaxFact,
    *,
    maximum_depth: int = 3,
    body_kinds: tuple[str, ...] = ("branch", "loop", "guard", "scope"),
) -> bool:
    """Whether one declaration nests bodies deeper than the ceiling a reader can hold.

    Definition
    ----------
    Walk the declaration and find the longest chain of constructs that open a body inside another
    body, counting a branch, a loop, a guarded block, and a scope. Report the declaration when that
    chain passes `maximum_depth`. Each level is a condition a reader has to carry from the line
    that opened it all the way down, and by the fourth level the line in front of them only makes
    sense together with three others somewhere above.

    A construct only adds a level where it is written deeper than the one holding it, which is the
    reader's own measure since indentation is what nesting looks like on the page. That is what
    keeps a chain of alternatives flat. Python spells the chain `elif` and hands over one branch,
    while Rust and C spell it `} else if {` and hand over a branch inside a branch, yet both read
    as one decision with several arms and neither costs a reader a level.

    Nesting is also where bugs hide, because the deepest line is the one reached by the fewest
    inputs and therefore the one a test is least likely to run. The usual repair is a guard clause
    that returns early, or lifting the innermost body into a function that names what it does.

    Evidence
    --------
    Each finding names the declaration and the deepest chain it holds, with the line each level
    opens on. The result is true for one declaration that nests too deeply.

    Exceptions
    ----------
    Expression structure is not nesting, so a call inside a comparison inside an argument counts
    nothing, and only a construct opening a body is counted. An arm of a chained alternative is not
    a level either, since it closes where the branch it continues closes and is never written
    deeper than it. The tree stops six levels below the declaration, so a body nested deeper than
    that arrives truncated and is measured at the bound rather than at its real depth. That
    under-reports and never over-reports, which is the right direction for a rule that asks a
    project to restructure a function. A construct a frontend states without a span is measured as
    written, because nothing then locates it against what holds it. A declaration whose family was
    never asked for carries no tree and is not judged. `body_kinds` names the constructs that open
    a body, so a language whose block construct this list has not met is configured rather than
    reimplemented.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def settle(orders):
           for order in orders:
               if order.is_open:
                   for item in order.items:
                       if item.is_taxed:
                           charge(item)

    Good
    ~~~~
    .. code-block:: python

       def settle(orders):
           for order in orders:
               if order.is_open:
                   settle_items(order)

       def settle_items(order):
           for item in order.items:
               if item.is_taxed:
                   charge(item)

    References
    ----------
    Generalizes SonarSource S134
    https://rules.sonarsource.com/python/RSPEC-134/
    Cites "Cognitive Complexity", a new way of measuring understandability
    https://www.sonarsource.com/resources/cognitive-complexity/
    Generalizes Clippy excessive_nesting
    https://rust-lang.github.io/rust-clippy/master/index.html#excessive_nesting
    Cites Ruff SIM102 collapsible-if
    https://docs.astral.sh/ruff/rules/collapsible-if/
    """
    return subject.tree is not None and nesting(subject.tree, body_kinds) > maximum_depth
