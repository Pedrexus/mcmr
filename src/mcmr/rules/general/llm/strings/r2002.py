from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import StringExpressionFact


class StringConstructionMechanism(StrEnum):
    LITERAL = auto()
    F_STRING = auto()
    STRING_TEMPLATE = auto()
    JINJA2 = auto()
    JOIN = auto()
    F_STRING_JOIN = auto()
    UNCERTAIN = auto()


@rule
async def string_construction_mechanism(
    subject: StringExpressionFact,
    backend: ClassificationBackend,
) -> StringConstructionMechanism:
    """Select a string mechanism from explicit construction requirements.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited construction facts and reduce
    them through a fixed decision table. The model identifies requirements but never chooses the
    mechanism. Literals own static text, f-strings own local expressions, `str.join` owns Python
    iterables, `string.Template` owns simple external placeholders, and Jinja2 owns template logic
    or contextual markup escaping.

    Evidence
    --------
    The frozen bundle cites the string boundary, its authors, dynamic values, iteration ownership,
    control flow, and escaping requirements. Missing, duplicate, conflicting, or uncited answers
    remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    SQL, shell, regular-expression, logging, localization, and security-sensitive APIs retain
    their own parameterization contracts. Ruff UP031, UP032, FLY002, and ISC003 plus Pylint R1713
    retain direct syntax diagnostics.

    Examples
    --------
    `f"Hello {user.name}"` is an `f_string`. Rendering rows in Python and joining them is
    `f_string_join`. An HTML email with template loops and escaping is `jinja2`.

    References
    ----------
    Cites "PEP 498, Literal String Interpolation"
    https://peps.python.org/pep-0498/
    Cites "The Python Standard Library", `string.Template`
    https://docs.python.org/3/library/string.html#template-strings
    Cites "Jinja documentation", template designer
    https://jinja.palletsprojects.com/en/stable/templates/
    Cites "PEP 8, Style Guide for Python Code", programming recommendations for `str.join`
    https://peps.python.org/pep-0008/#programming-recommendations
    """
    return await backend.classify(
        subject,
        category=StringConstructionMechanism,
        instructions=(
            "Ask the selected judgment backend for four independently cited construction"
            "facts and reduce them through a fixed decision table. The model identifies"
            "requirements but never chooses the mechanism. Literals own static text,"
            "f-strings own local expressions, `str.join` owns Python iterables,"
            "`string.Template` owns simple external placeholders, and Jinja2 owns"
            "template logic or contextual markup escaping."
        ),
    )
