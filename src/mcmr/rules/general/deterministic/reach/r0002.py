from ..... import rule
from .....facts import SymbolReachFact, Visibility
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted

# A module-scope name is the only declaration a graph can prove nothing reaches. A method is
# reached through a receiver whose type is often not stated, and a property is read rather than
# called, so neither leaves an edge that would prove the absence of a caller.
_REACHABLE_KINDS = frozenset({"class", "function"})


@rule
def file_local_public_declaration(subject: SymbolReachFact) -> CountReport:
    """Count public declarations only their own file ever uses.

    Definition
    ----------
    Report a public declaration that at least one reference reaches, where every one of those
    references sits in the file that declares it. A name published to the whole repository but
    used in exactly one place is stating a contract it does not have. Making it nonpublic tells a
    reader the truth, and it frees the declaration to change without a repository-wide search.

    This is the ordinary way a module accumulates surface. A helper is written public because
    everything else nearby is public, and nothing ever calls it from outside.

    Evidence
    --------
    Each finding names the declaration, its kind, and how many references its own file makes
    against the nothing every other file makes. The repair is a choice, because a name is either
    an interface nobody adopted yet or a helper that was never meant to be one. The value is the
    number of such declarations.

    Exceptions
    ----------
    A module a test runner collects is skipped, since its declarations are reached by name. A
    published API, a framework hook, and a plugin entry point are reached from outside the
    repository, so their reference counts understate them. A declaration a test file reaches is
    reached from another file and is not counted here.

    Examples
    --------
    A public `def parse_header(line)` that only its own module calls returns `1` and should become
    `_parse_header` or move inside its single caller. The same function called from two modules
    returns `0`.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "A Philosophy of Software Design", on narrow interfaces
    Cites "Effective Go", names and exported identifiers
    https://go.dev/doc/effective_go#names
    """
    if subject.is_test_module:
        return Reported(value=0)
    local = [
        declaration
        for declaration in subject.declarations
        if declaration.kind in _REACHABLE_KINDS
        and declaration.visibility is Visibility.PUBLIC
        and declaration.own_file_references > 0
        and declaration.other_file_references == 0
    ]
    return Reported(
        value=len(local),
        findings=tuple(
            Finding(
                message=(
                    f"`{declaration.qualname}` is a public {declaration.kind} read "
                    f"{counted(declaration.own_file_references, 'time')} inside this file and "
                    f"nowhere outside it"
                ),
                span=subject.span,
                measurements=(
                    Measurement(
                        name="references from its own file",
                        value=declaration.own_file_references,
                    ),
                    Measurement(name="references from anywhere else", value=0),
                ),
                repair=Choice(
                    question=f"say what `{declaration.qualname}` is for",
                    options=(
                        "make it private, since nothing outside reads it",
                        "keep it public where it is an interface this file publishes",
                    ),
                ),
            )
            for declaration in local
        ),
    )
