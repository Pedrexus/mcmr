from ..... import rule
from .....facts import SymbolReachFact, Visibility
from .....models import Count

# A module-scope name is the only declaration a graph can prove nothing reaches. A method is
# reached through a receiver whose type is often not stated, and a property is read rather than
# called, so neither leaves an edge that would prove the absence of a caller.
_REACHABLE_KINDS = frozenset({"class", "function"})


@rule
def unreferenced_public_declaration(subject: SymbolReachFact) -> Count:
    """Count public declarations no reference in the repository reaches.

    Definition
    ----------
    Read every declaration one module states and report a public one that no call, construction,
    inheritance, or import reaches anywhere in the repository, including its own file. A public
    name is a promise to the rest of the codebase, and a promise nobody took up is either dead
    code or an interface that was never wired. Either way it costs a reader who has to decide
    whether it matters.

    A name-based dead-code search cannot answer this, because it cannot tell a shadowed local from
    the declaration it hides. A resolved graph can, which is why this rule needs one.

    Evidence
    --------
    Each finding names the declaration, its kind, and its declaring module. The value is the number
    of unreferenced public declarations.

    Exceptions
    ----------
    Only a module-scope class or callable is judged, so a nested definition a caller passes as a
    value is left alone. A method is reached through a receiver whose
    type is often not stated and a property is read rather than called, so neither leaves an edge
    that could prove nothing reaches it. A module a test runner collects is skipped outright,
    because a runner reaches its tests by name and no call to them exists to find. A declaration
    a framework reaches by name, an entry point a packaging manifest lists, and a plugin a registry
    loads at runtime are all reached in ways no static graph sees. A public API that exists for
    downstream users is legitimately
    unreferenced inside its own repository, so a library excludes its published modules rather
    than deleting them.

    Examples
    --------
    A public `def normalize(value)` that nothing calls returns `1`. A `_normalize` used only in
    its own file is not counted, because a nonpublic name promises nothing. A class only its tests
    construct is reached and is not counted.

    A decorated declaration is skipped, because a decorator is how a framework claims a name and
    the framework reaches it without ever calling it.

    One limit remains. A symbol re-exported through a package initializer is reached through an
    import of its module rather than of itself, and a class read only through one of its members,
    such as an enum accessed by name, leaves no edge either. Both read as unreached.

    References
    ----------
    Cites "Vulture documentation", dead code detection and its stated confidence limits
    https://github.com/jendrikseipp/vulture
    Cites Pylint W0238 unused-private-member
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/unused-private-member.html
    Cites "Refactoring", remove dead code
    """
    if subject.is_test_module:
        return 0
    return sum(
        declaration.is_module_scope
        and not declaration.is_decorated
        and declaration.kind in _REACHABLE_KINDS
        and declaration.visibility is Visibility.PUBLIC
        and declaration.own_file_references == 0
        and declaration.other_file_references == 0
        for declaration in subject.declarations
    )
