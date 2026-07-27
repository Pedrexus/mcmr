from ..... import rule
from .....facts import CallFact, CallSite
from .....models import Count, SourceRewrite, Unwrap


def has_boolean_operand(call: CallSite) -> bool:
    """Whether one unshadowed `bool` call converts a single operand already typed Boolean."""
    return (
        call.qualified_name == "builtins.bool"
        and not call.is_shadowed
        and len(call.arguments) == 1
        and not call.keyword_names
        and call.arguments[0].resolved_type == "bool"
    )


@rule
def redundant_boolean_conversion(subject: CallFact) -> Count:
    """Count builtin `bool` calls whose operands are already proven Boolean.

    Definition
    ----------
    Resolve calls to the unshadowed builtin `bool` with exactly one positional argument. Report a
    call only when the operand is a Boolean literal, comparison, `not` expression, conditional with
    Boolean branches, Boolean operation whose every operand is proven Boolean, a name explicitly
    annotated as `bool`, or an unshadowed standard predicate with an exact Boolean return. Emit a
    safe source edit that removes the conversion while retaining parentheses and UTF-8 offsets.

    Evidence
    --------
    Each finding records the source range and the AST kind that proves the operand Boolean. The
    value is the number of redundant conversions.

    Exceptions
    ----------
    Truthiness is not Boolean identity. Do not report `bool(sequence)`, `bool(mapping)`,
    `bool(optional)`, an unannotated value, or an `and` or `or` expression containing any operand
    that may return a non-Boolean object. A shadowed `bool`, `all`, `any`, `callable`, `hasattr`,
    `isinstance`, or `issubclass` suppresses inference. Comments inside the call suppress the edit
    but retain the diagnostic.

    Examples
    --------
    Bad
    ~~~
    `bool(enabled)` is redundant when `enabled: bool`. So are `bool(value is None)` and
    `bool(all(checks))` when the builtin names are unshadowed.

    Good
    ~~~~
    `bool(items)` intentionally converts sequence truthiness. `bool(fragile)` remains necessary
    when `fragile` is a tuple of findings rather than an exact Boolean.

    References
    ----------
    Cites "The Python Language Reference", truth value testing
    https://docs.python.org/3/library/stdtypes.html#truth-value-testing
    Cites "The Python Standard Library", `bool`
    https://docs.python.org/3/library/functions.html#bool
    Cites "The Python Language Reference", Boolean operations
    https://docs.python.org/3/reference/expressions.html#boolean-operations
    """
    return sum(has_boolean_operand(call) for call in subject.calls)


@redundant_boolean_conversion.fix(is_default=True)
def remove_redundant_bool(subject: CallFact) -> list[SourceRewrite]:
    """Keep the Boolean operand and drop the conversion wrapped around it."""
    return [
        Unwrap(target=call.node, keep=call.arguments[0].node)
        for call in subject.calls
        if has_boolean_operand(call)
        and call.node is not None
        and call.arguments[0].node is not None
    ]
