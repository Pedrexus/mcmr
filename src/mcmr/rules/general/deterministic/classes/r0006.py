from ..... import rule
from .....facts import ClassFact, Visibility
from .....models import Count


@rule
def nonpublic_top_level_class_count(subject: ClassFact) -> Count:
    """Count nonpublic classes declared at namespace scope.

    Definition
    ----------
    Inspect class declarations in the execution scope of a module, package, or namespace, including
    declarations under control flow. Report a class whose resolved visibility is not public. A
    namespace-scope class is an explicit type and should carry a public name when it needs an
    identity at that scope. A class nested inside a function, a method, or another class can stay
    nonpublic because its enclosing declaration already limits the namespace it lives in.

    Every language that expresses visibility takes part, whichever way it spells it. A provider
    resolves the leading underscore in Python, the lowercase initial in Go, a missing `pub` in
    Rust, `private` or package private in Java and C#, an unexported declaration in TypeScript, and
    an anonymous namespace in C++. Languages differ on how much they expect at this scope, so the
    rule reports the count and a project policy decides what that count may be. A Python or Java
    project usually holds it at zero while a Rust or Go project deliberately keeps most of its
    namespace-scope types unexported.

    Evidence
    --------
    Each finding identifies the full class declaration range, the class name, its resolved
    visibility, and its namespace scope. The result value is the number of nonpublic namespace
    scope classes.

    Exceptions
    ----------
    Classes nested inside functions, methods, or other classes are not inspected. A name a language
    reserves for its own protocol, such as a Python dunder, is accepted as deliberate. This rule
    does not infer whether a public class belongs in a narrower module.

    Examples
    --------
    A module-level `class _Parser` in Python is reported, as are an unexported Go `type parser
    struct` and a Rust `struct Parser` without `pub`. `class Parser` and `class __Generated__` are
    accepted. A local `class _State` inside `build_parser`, a method, or another class is also
    accepted because it has no identity at namespace scope.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", public and internal interface conventions
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "The Python Tutorial", private variables
    https://docs.python.org/3/tutorial/classes.html#private-variables
    Cites "Google Python Style Guide", nested classes and functions
    https://google.github.io/styleguide/pyguide.html#262-nested-local-inner-classes-and-functions
    Cites "Effective Go", names and exported identifiers
    https://go.dev/doc/effective_go#names
    """
    return sum(
        item.scope == "module" and item.visibility is not Visibility.PUBLIC
        for item in subject.classes
    )
