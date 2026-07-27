from ..... import rule
from .....facts import ImportBindingFact


@rule
def cross_module_project_constant_import(
    subject: ImportBindingFact,
) -> bool:
    """Detect a project-owned constant imported outside its defining module.

    Definition
    ----------
    Detect public or single-underscore uppercase constants defined by top-level assignments.
    Resolve project-relative and absolute `from` imports against those definitions. Report every
    import from a different project module. Constants remain private implementation details rather
    than becoming shared state through a `constants.py` module.

    Evidence
    --------
    Each finding cites the constant definition and exact importing statement. The Boolean result
    identifies one proven cross-module project constant import.

    Exceptions
    ----------
    Third-party symbols and imports guarded by `TYPE_CHECKING` are excluded. Wildcard imports,
    dynamically created names, and attribute access through an imported module are not inferred.
    Imports inside the defining module are not cross-module uses.

    Examples
    --------
    Bad
    ~~~
    `from .service import _TIMEOUT` and `from .service import TIMEOUT` both expose project constant
    state across a module boundary.

    Good
    ~~~~
    `_TIMEOUT` remains in `service.py`, while consumers call a public operation that owns the
    relevant behavior. `from third_party import TIMEOUT` is outside the project definition graph.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", constants naming convention
    https://peps.python.org/pep-0008/#constants
    Cites "The Python Language Reference", import system reference
    https://docs.python.org/3/reference/import.html
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    imported = subject.imported_name or subject.name
    return subject.is_project_owned and imported.lstrip("_").isupper()
