from ..... import rule
from .....facts import ModuleFact
from .....models import Count


@rule
def dependency_safe_constant_order(subject: ModuleFact) -> Count:
    """Keep module constants at their earliest dependency-safe top-level position.

    Definition
    ----------
    Detect public uppercase names assigned by top-level assignments. A constant without local
    initializer dependencies belongs in the contiguous constant block after the module imports. A
    constant that loads a locally defined class, function, or assigned name belongs immediately
    after its latest local dependency. Existing constant declarations may remain contiguous, while
    unrelated classes, functions, and executable assignments between the valid anchor and the
    constant are reported.

    Evidence
    --------
    Each finding identifies the constant declaration, its import or dependency anchor, every
    unrelated intervening statement, and the number of those statements. The result value is the
    number of declarations that can move earlier without crossing an initializer dependency.

    Exceptions
    ----------
    The module docstring and dunder metadata such as `__all__` and `__version__` do not affect
    placement. Imports establish the initial anchor. Dynamic dependencies hidden behind attribute
    lookup or string evaluation are not inferred. Deferred names inside a callable initializer may
    require project-specific review before an automatic move.

    Examples
    --------
    A literal `TIMEOUT = 30` below an unrelated `Service` class is reported because it belongs
    after imports. A self-describing `class CategoryDecision(DecisionTable[Category])` is accepted
    as a type declaration rather than mistaken for a constant assignment. `DERIVED = BASE + 1`
    directly after `BASE = 1` is also accepted.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", module imports convention
    https://peps.python.org/pep-0008/#imports
    Cites "PEP 8, Style Guide for Python Code", constants convention
    https://peps.python.org/pep-0008/#constants
    Cites "The Python Language Reference", execution model
    https://docs.python.org/3/reference/executionmodel.html
    """
    return sum(
        placement.intervening_statement_count > 0 for placement in subject.constant_placements
    )
