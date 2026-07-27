from ..... import rule
from .....facts import TryBlockFact
from .....models import Count, Move, Placement, SourceRewrite


@rule
def broad_try_literal_setup(subject: TryBlockFact) -> Count:
    """Count literal local setup assignments needlessly protected by a broad `try`.

    Definition
    ----------
    Inspect ordinary `try` statements inside functions. Report a `try` when its body starts with
    one or more assignments of a literal `ast.Constant` to one simple local name, another body
    statement follows, and that next statement contains an explicit operation that can raise.
    Calls, imports, attribute or subscript access, arithmetic, comparison, assertion, raising,
    iteration, context management, and awaiting are the exact protected-operation set. Moving the
    literal assignments immediately before the `try` narrows which failures the handlers catch.

    Evidence
    --------
    Each finding identifies every movable local name, the exact source range of the leading setup,
    and the first protected operation. No automatic edit is offered because comments and the
    indentation of a compound statement require a concrete-syntax transformation. The value is the
    number of `try` regions opening with movable literal setup.

    Exceptions
    ----------
    Abstain at module or class scope, for `try` statements with `finally`, for exception-group
    `try*`, and when a candidate name is declared `global` or `nonlocal`. Annotated, chained,
    destructuring, attribute, subscript, computed, or type-commented assignments are not proven
    non-raising. A `try` containing only literal setup and a non-raising return is not reported.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           mode = "rb"
           payload = stream.read()
       except OSError:
           recover()

    Good
    ~~~~
    .. code-block:: python

       mode = "rb"
       try:
           payload = stream.read()
       except OSError:
           recover()

    Keep a computed setup expression inside when evaluating it belongs to the recovery boundary.

    References
    ----------
    Cites "The Python Tutorial", Handling Exceptions
    https://docs.python.org/3.14/tutorial/errors.html#handling-exceptions
    Cites "The Python Language Reference", the try statement
    https://docs.python.org/3.14/reference/compound_stmts.html#the-try-statement
    Cites "Clean Code in Python", Error Handling
    """
    return sum(
        region.leading_literal_assignment_count > 0 and region.has_following_raising_operation
        for region in subject.regions
    )


@broad_try_literal_setup.fix(is_default=True)
def move_setup_outside_try(subject: TryBlockFact) -> list[SourceRewrite]:
    """Lift the literal setup above the statement that protects it."""
    return [
        Move(target=assignment, anchor=region.statement, placement=Placement.BEFORE)
        for region in subject.regions
        if region.statement is not None and region.has_following_raising_operation
        for assignment in region.leading_assignments
    ]
