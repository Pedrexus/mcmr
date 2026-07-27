from ..... import rule
from .....facts import ImportBindingFact
from .....models import Occurrence


@rule
def relative_import_beyond_package(subject: ImportBindingFact) -> Occurrence:
    """Report a relative import climbing past the top-level package it starts in.

    Definition
    ----------
    Count the leading dots one relative import states and compare them against the package holding
    the importing module. One dot names that package, two name its parent, and an import stating
    more dots than the package has components leaves the tree entirely and raises `ImportError`
    the first time the module loads. A package initializer is its own package, so it affords one
    more level than a module sitting beside it.

    This needs no interpreter and no installed environment. Both halves of the comparison, the
    dots in the statement and the package derived from the file layout, are in the repository, so
    the answer is arithmetic rather than a resolution attempt.

    Evidence
    --------
    The finding names the import and the module stating it. The result reports whether the import
    reaches above the top-level package.

    Exceptions
    ----------
    A module in no package at all is not judged. There is no top level for it to exceed, the
    interpreter answers with a different failure, and the file is usually a script rather than
    part of a tree. A dot count within the package is correct however deep it goes, since depth is
    a separate question the relative-import-depth rule already asks.

    Examples
    --------
    Bad
    ~~~
    `from ...shared import Client` inside `pkg/sub/module.py`, whose package `pkg.sub` has two
    components, climbs one level above `pkg`.

    Good
    ~~~~
    `from ..shared import Client` inside `pkg/sub/module.py` reaches `pkg.shared`, which exists.

    References
    ----------
    Generalizes Pylint E0402 relative-beyond-top-level
    https://pylint.readthedocs.io/en/latest/user_guide/messages/error/relative-beyond-top-level.html
    Cites "PEP 328, Imports and Relative Imports", which defines what a leading dot counts against
    https://peps.python.org/pep-0328/
    Cites "The CPython source", the check this reproduces
    https://docs.python.org/3/reference/import.html#package-relative-imports
    """
    if not subject.is_relative or subject.declaration is None:
        return False
    stated = subject.declaration.text.removeprefix("from ")
    level = len(stated) - len(stated.lstrip("."))
    components = subject.importer_module.split(".")
    owned = len(components) if subject.span.path.endswith("__init__.py") else len(components) - 1
    return owned > 0 and level > owned
