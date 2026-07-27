from ..... import rule
from .....facts import SymbolReachFact
from .....models import Count


@rule
def repository_wide_declaration(subject: SymbolReachFact, *, maximum_packages: int = 3) -> Count:
    """Count declarations whose use spreads across more packages than a contract should.

    Definition
    ----------
    Report a declaration that more than `maximum_packages` distinct top-level packages reach. A
    name used that widely is load-bearing whether or not anyone declared it so, because every
    package that reaches it now depends on its exact shape, and changing it means changing all of
    them at once.

    Spread is not a defect. It is the evidence that tells a project which declarations are its real
    contracts, so those can be documented, versioned, and tested as contracts rather than
    discovered during a refactor.

    Evidence
    --------
    Each finding names the declaration and the packages, directories, and files that reach it. The
    value is the number of declarations spreading past the configured width.

    Exceptions
    ----------
    A shared foundation is supposed to spread. A base model, a logger, and a configuration reader
    are wide by design, and a project raises the ceiling or excludes the module that owns them. A
    declaration reached from only one package, however many files that package holds, is local to
    that package and is not counted.

    Examples
    --------
    A `Model` base class reached from six packages returns `1` and deserves a stated contract. A
    helper reached from four files of one package returns `0`.

    References
    ----------
    Cites "Clean Architecture", the stable dependencies principle
    Cites "Agile Software Development", the common closure principle
    Cites "A Philosophy of Software Design", on deep modules
    """
    return sum(
        declaration.referencing_packages > maximum_packages for declaration in subject.declarations
    )
