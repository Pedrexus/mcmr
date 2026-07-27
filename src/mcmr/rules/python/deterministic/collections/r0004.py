from ..... import rule
from .....facts import CallFact, CallSite
from .....models import Count, FixSafety, Replace, SourceRewrite


def is_rewritable_construction(call: CallSite) -> bool:
    """Whether one unshadowed `tuple` call states a single argument a display can carry."""
    return (
        call.qualified_name == "builtins.tuple"
        and not call.is_shadowed
        and len(call.arguments) == 1
        and not call.keyword_names
        and not call.has_starred_arguments
    )


@rule
def explicit_tuple_construction(subject: CallFact) -> Count:
    """Count explicit calls to the builtin tuple constructor.

    Definition
    ----------
    Report every unshadowed `tuple(...)` call. MCMR prefers list comprehensions and list displays
    while Pydantic model fields own any required tuple coercion at the data boundary. Literal
    tuples and tuple type annotations are outside this rule.

    Evidence
    --------
    Each finding records the call location and positional argument count. Calls with zero or one
    positional argument and no keyword produce an unsafe autofix to a list display because tuple
    hashability, equality, and mutation semantics can be observable. The value is the number of
    unshadowed `tuple` constructor calls.

    Exceptions
    ----------
    A source file that binds the name `tuple` is conservatively excluded because the call may
    target project code. Comments, incomplete source ranges, keywords, and multiple arguments keep
    the finding but suppress the edit.

    Examples
    --------
    Bad
    ~~~
    `items = tuple(normalize(item) for item in source)` materializes an immutable container.

    Good
    ~~~~
    `items = [normalize(item) for item in source]` states the preferred collection directly.
    A Pydantic field annotated as `tuple[Item, ...]` may receive the list and validate its stored
    representation at the boundary.

    References
    ----------
    Cites "Fluent Python", chapter 2, An Array of Sequences
    Cites "The Python Language Reference", list displays
    https://docs.python.org/3.14/reference/expressions.html#list-displays
    Cites "Pydantic documentation", standard library types, tuples
    https://docs.pydantic.dev/latest/api/standard_library_types/#tuples
    """
    return sum(
        call.qualified_name == "builtins.tuple" and not call.is_shadowed for call in subject.calls
    )


@explicit_tuple_construction.fix(is_default=False, safety=FixSafety.REVIEW)
def replace_with_list(subject: CallFact) -> list[SourceRewrite]:
    """Build the sequence as a list display, which the house style prefers."""
    return [
        Replace(target=call.node, source=f"list({call.arguments[0].text})")
        for call in subject.calls
        if call.node is not None and is_rewritable_construction(call)
    ]


@explicit_tuple_construction.fix(is_default=False, safety=FixSafety.REVIEW)
def replace_with_tuple_literal(subject: CallFact) -> list[SourceRewrite]:
    """Keep tuple semantics while dropping the constructor call around them."""
    return [
        Replace(target=call.node, source=f"(*{call.arguments[0].text},)")
        for call in subject.calls
        if call.node is not None and is_rewritable_construction(call)
    ]
