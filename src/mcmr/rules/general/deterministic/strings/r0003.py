from ..... import rule
from .....facts import StringExpressionFact
from .....models import Count


@rule
def decorative_repeated_separator_count(
    subject: StringExpressionFact, *, minimum_repetitions: int = 3
) -> Count:
    """Find fixed repeated-string expressions used as decorative separators.

    Definition
    ----------
    Report multiplication of a nonempty punctuation-only string literal by a fixed integer at or
    above `minimum_repetitions`. Recognize either operand order and a conservative set of common
    separator characters. Prefer a semantic heading, structured logger field, or natural spacing
    instead of manufacturing a visual rule whose width carries no program meaning.

    Evidence
    --------
    Each finding records the expression range, separator literal, and fixed repetition count. The
    value is the number of decorative separator expressions.

    Exceptions
    ----------
    Alphanumeric strings, whitespace, control bytes, variable counts, and repetitions below the
    threshold are excluded because they may encode data, padding, or a protocol requirement.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       logger.info("-" * 30)
       banner = 12 * "="

    Good
    ~~~~
    .. code-block:: python

       logger.info("Dependency checks")
       padding = "0" * width

    References
    ----------
    Cites "The Python Language Reference", binary arithmetic operations and sequence repetition
    https://docs.python.org/3/reference/expressions.html#binary-arithmetic-operations
    Cites "Python HOWTOs", structured contextual logging
    https://docs.python.org/3/howto/logging-cookbook.html
    """
    punctuation = set("-_*=~.#")
    return sum(
        bool(expression.repeated_literal)
        and set(expression.repeated_literal) <= punctuation
        and expression.repetition_count >= minimum_repetitions
        for expression in subject.expressions
    )
