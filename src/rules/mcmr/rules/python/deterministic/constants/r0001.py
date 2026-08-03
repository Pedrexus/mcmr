from ..... import rule
from .....facts import SymbolFact
from .....query import CountQuery
from .....table import Table
from ..symbol_relations import SymbolRelations, public_constant_query


@rule("PY-CONS0001")
def public_module_constant(subject: Table[SymbolFact]) -> CountQuery:
    """Find project module constants exposed without a leading underscore.

    Definition
    ----------
    Inspect top-level assignments and annotated assignments whose names use the public uppercase
    constant convention. Report names such as `TIMEOUT` and `JSON_ADAPTER`. Project file constants
    are implementation details by default and should use one leading underscore. Cross-module
    imports are handled separately by the project constant import rule.

    Evidence
    --------
    Each finding identifies the public constant declaration and its exact source line. Private
    uppercase constants, ordinary variables, instance attributes, class attributes, and lowercase
    implementation state are not reported. The value is the number of public uppercase module
    constants.

    Exceptions
    ----------
    Interpreter-reserved dunder names are excluded. A deliberate public constant API can disable
    this preference for its defining file.

    Examples
    --------
    Bad
    ~~~
    `DEFAULT_TIMEOUT = 30` exposes project-owned constant state from its module.

    Good
    ~~~~
    `_DEFAULT_TIMEOUT = 30` keeps the constant private to its defining module.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", constants naming convention
    https://peps.python.org/pep-0008/#constants
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    return public_constant_query(SymbolRelations(subject))
