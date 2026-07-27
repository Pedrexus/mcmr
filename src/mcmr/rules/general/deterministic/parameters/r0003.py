from ..... import rule
from .....facts import FunctionFact
from .....models import Count

# What a Boolean is called in each language a frontend fills. A parameter typed with any of these
# reads as a flag at the call site whatever its name is.
_BOOLEAN = frozenset({"bool", "boolean", "Boolean", "_Bool", "BOOL"})


@rule
def positional_boolean_parameter(subject: FunctionFact) -> Count:
    """Count Boolean parameters a caller must pass by position.

    Definition
    ----------
    Report a parameter typed Boolean that a caller cannot name at the call site. The call then
    reads `render(document, True, False)`, which says nothing about what is true, and a reader has
    to open the signature to find out. Worse, the two flags can be transposed and the program keeps
    compiling, so the mistake surfaces as behavior rather than as an error.

    The repair is not always a keyword argument. Two Booleans usually mean the function does two
    things, and splitting it removes the flags along with the ambiguity.

    Evidence
    --------
    Each finding names the function, the parameter, and its position. The value is the number of
    positional Boolean parameters.

    Exceptions
    ----------
    A parameter a language forces into position, such as the receiver, is not counted. A signature
    an external contract fixes, like a framework callback, is a reason to exclude the module rather
    than to fight the interface. A single Boolean whose name reads as a sentence at the call site,
    such as `sorted(values, reverse)`, is the borderline case this rule deliberately still reports,
    because the next Boolean added beside it is the one that breaks.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def render(document, inline: bool, minified: bool): ...

       render(document, True, False)

    Good
    ~~~~
    .. code-block:: python

       def render(document, *, inline: bool, minified: bool): ...

       render(document, inline=True, minified=False)

    The same shape in Rust is `fn render(document: &Document, inline: bool, minified: bool)`, and
    the same repair is a small options struct or two functions.

    References
    ----------
    Cites "Refactoring", remove flag argument
    https://refactoring.com/catalog/removeFlagArgument.html
    Cites "Clean Code", chapter 3, flag arguments
    Generalizes Ruff FBT001 boolean-type-hint-positional-argument
    Generalizes Ruff FBT002 boolean-default-value-positional-argument
    """
    return sum(
        (parameter.type_name in _BOOLEAN or parameter.has_boolean_annotation)
        and not parameter.is_keyword_only
        and not parameter.is_receiver
        for parameter in subject.parameters
    )
