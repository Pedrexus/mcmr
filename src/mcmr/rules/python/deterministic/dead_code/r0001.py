from ..... import rule
from .....facts import FunctionFact, Visibility
from .....models import FixSafety, Remove, SourceRewrite


@rule
def unreferenced_private_function(subject: FunctionFact) -> bool:
    """Detect an undecorated private module function without project reference evidence.

    Definition
    ----------
    Inspect module functions with one leading underscore and no decorator. Retain a function when
    another source location loads its name, accesses an attribute with the same name, or contains
    that name as a string for dynamic lookup. A recursive reference inside the candidate does not
    make an otherwise unreachable function live. Dunder hooks, methods, classes, public API, and
    decorated registrations are outside the rule. Ruff continues to own unused imports and local
    variables.

    Evidence
    --------
    Each finding points to the definition and records the high-confidence private-function scope.
    The rule reuses the project AST prepared by the collector and performs no file read or second
    parse.

    Exceptions
    ----------
    Dynamic lookup assembled from multiple strings and external consumers outside the scanned
    project cannot be proved. The rule prefers a false negative when any plausible project
    reference exists. Public library functions are deliberately excluded because repository-only
    analysis cannot know their consumers.

    Examples
    --------
    Bad
    ~~~
    `def _obsolete(): ...` with no project reference produces one finding.

    Good
    ~~~~
    `_parse` passed as a callback, `module._parse()`, and `getattr(module, "_parse")` retain
    the function. `@router.register` and public functions are outside the candidate set.

    References
    ----------
    Generalizes Pylint W0238 unused-private-member
    Cites "Vulture documentation", unused function detection and confidence
    https://github.com/jendrikseipp/vulture
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    return (
        subject.scope == "module"
        and subject.visibility is not Visibility.PUBLIC
        and not subject.decorators
        and subject.reference_count == int(subject.is_recursive)
    )


@unreferenced_private_function.fix(is_default=True, safety=FixSafety.REVIEW)
def remove_unreferenced_private_function(subject: FunctionFact) -> list[SourceRewrite]:
    """Delete a nonpublic function nothing in its own module calls."""
    if subject.definition is None:
        return []
    return [Remove(target=subject.definition)]
