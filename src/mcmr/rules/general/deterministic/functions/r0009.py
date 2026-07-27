from ..... import rule
from .....facts import FunctionFact, Visibility
from .....models import FixSafety, Inline, SourceRewrite


@rule
def transparent_unary_wrapper(subject: FunctionFact) -> bool:
    """Detect a public unary function that only forwards one argument.

    Definition
    ----------
    Report a synchronous public module function or static method only when it has one required
    parameter and its sole executable statement returns one call with that parameter unchanged.
    A direct callable alias or direct call expresses the same dispatch without another boundary.

    Evidence
    --------
    Each finding identifies the wrapper, forwarded callable, and complete source range. The rule
    does not infer semantic similarity or inspect nested behavior.

    Exceptions
    ----------
    Instance methods, class methods, private helpers, asynchronous adapters, decorators other than
    `staticmethod`, overloads, defaults, argument adaptation, result transformation, and recursive
    calls are excluded. A narrowing annotation alone does not preserve a wrapper when the called
    function already exposes the same narrowing contract. Keep a wrapper when its distinct
    `__name__`, signature, documentation, instrumentation, or compatibility boundary is an
    intentional public contract.

    Examples
    --------
    Bad
    ~~~
    `def normalize(value: str) -> str: return inflection.underscore(value)` adds only a forwarding
    frame.

    Good
    ~~~~
    `normalize = inflection.underscore` gives the callable a project name directly. A function
    that validates, transforms, logs, awaits, or combines arguments remains a real boundary.
    Inside a method, call `inspect.isclass(value)` directly instead of wrapping it as `is_class`.

    References
    ----------
    Cites "The Python Language Reference", assignment statements
    https://docs.python.org/3/reference/simple_stmts.html#assignment-statements
    Cites "A Philosophy of Software Design", chapters 4 and 7
    Cites "Clean Code", chapter 3
    """
    decorators = set(subject.decorators)
    is_allowed_decorator = not decorators or decorators == {"staticmethod"}
    is_candidate = (
        subject.scope in {"module", "method"}
        and subject.visibility is Visibility.PUBLIC
        and not subject.is_async
        and is_allowed_decorator
        and len(subject.parameters) == 1
        and subject.returns_single_call
        and subject.forwards_only_parameter_unchanged
        and not subject.is_overload
        and not subject.is_recursive
    )
    return is_candidate


@transparent_unary_wrapper.fix(is_default=True, safety=FixSafety.REVIEW)
def inline_transparent_wrapper(subject: FunctionFact) -> list[SourceRewrite]:
    """Replace the single reference with the helper body, then delete the declaration."""
    if subject.definition is None or subject.body_expression is None or not subject.references:
        return []
    return [
        Inline(
            declaration=subject.definition,
            body=subject.body_expression,
            references=subject.references,
        )
    ]
