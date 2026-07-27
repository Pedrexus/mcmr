from ..... import rule
from .....facts import FunctionFact
from .....models import Count

# What a Boolean is called in each language a frontend fills. A parameter typed with any of these
# reads as a flag whatever it is named and wherever it sits in the list.
_BOOLEAN = frozenset({"bool", "boolean", "Boolean", "_Bool", "BOOL"})


@rule
def boolean_parameter_count(subject: FunctionFact) -> Count:
    """Count the flags one callable takes, wherever a caller passes them.

    Definition
    ----------
    Count every parameter a callable declares whose type is Boolean or whose default is Boolean,
    excluding the receiver a language passes implicitly. Each flag doubles the states the body has
    to be correct in, so three of them describe eight callables sharing one name and one test
    suite, and the ones nobody exercises are the ones that break.

    This counts a keyword-only flag as well as a positional one. Naming a flag at the call site
    fixes readability, which is what the neighbouring positional-flag rule is about, and it does
    nothing about the state space, which is what this rule measures. The repair here is to split
    the callable or to replace the flags with one closed set of named behaviors.

    The measure is language-neutral because a flag is. A Rust `fn` taking four `bool` parameters, a
    TypeScript function taking four `boolean` ones, and a Python function taking four annotated
    `bool` ones are one design decision spelled three ways, so one rule answers for all of them.

    Evidence
    --------
    Each finding records the callable range and every counted parameter with its declared type. The
    value is the number of Boolean parameters, and a project policy owns the ceiling.

    Exceptions
    ----------
    The receiver is never counted, since a caller does not choose it. A signature an external
    contract fixes, such as a framework callback or a trait implementation, is a reason to exclude
    the module rather than to fight the interface. A parameter typed as a closed set of two named
    values is not a Boolean and is not counted, which is exactly the repair this rule points at.

    Examples
    --------
    `def render(document, *, inline: bool, minified: bool, strict: bool)` returns `3`, and so does
    `fn render(document: &Document, inline: bool, minified: bool, strict: bool)`. Replacing them
    with one `mode: RenderMode` parameter returns `0`.

    References
    ----------
    Generalizes Clippy fn_params_excessive_bools
    https://rust-lang.github.io/rust-clippy/master/index.html#fn_params_excessive_bools
    Cites Ruff FBT001 boolean-type-hint-positional-argument
    Cites Ruff FBT002 boolean-default-value-positional-argument
    Cites "Refactoring", remove flag argument
    https://refactoring.com/catalog/removeFlagArgument.html
    Cites "Clean Code", chapter 3, flag arguments
    """
    return sum(
        not parameter.is_receiver
        and (
            parameter.type_name in _BOOLEAN
            or parameter.has_boolean_annotation
            or parameter.has_boolean_default
        )
        for parameter in subject.parameters
    )
