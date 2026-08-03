import polars as pl

from ..... import rule
from .....facts import ImportBindingFact
from .....query import FindingQuery, RuleQuery
from .....table import ImportBindingRelation, Table


@rule("PY-CONS0002")
def cross_module_project_constant_import(
    subject: Table[ImportBindingFact],
) -> RuleQuery[bool]:
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
    frame = subject.lazy(ImportBindingRelation.FACTS)
    imported = (
        pl.when(pl.col("imported_name") != "")
        .then(pl.col("imported_name"))
        .otherwise(pl.col("name"))
        .str.strip_chars_start("_")
    )
    value = pl.col("is_project_owned") & imported.str.contains(r"^[A-Z][A-Z0-9_]*$")
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame, value, "cross module project constant import"
        ),
    )
