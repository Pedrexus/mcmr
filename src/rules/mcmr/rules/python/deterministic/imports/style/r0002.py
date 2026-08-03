import polars as pl

from ...... import rule
from ......facts import ImportBindingFact
from ......query import FindingQuery, RuleQuery
from ......table import ImportBindingRelation, Table


@rule("PY-IMPO0002")
def project_private_import(
    subject: Table[ImportBindingFact],
) -> RuleQuery[bool]:
    """Detect an import that crosses a project-owned nonpublic boundary.

    Definition
    ----------
    Report an import statement whose resolved project module holds a path component beginning with
    one underscore, or whose `from` import requests a member beginning with one underscore. The
    underscore is how Python states that a name is an implementation detail, so an import crossing
    it is a dependency the author of that module never agreed to keep working.

    Relative imports are project-owned by construction. An absolute import qualifies only when the
    module it names exists in the analyzed snapshot, which is what keeps a third-party package's
    own private spelling out of the findings. The judgment is made once per statement rather than
    once per alias, since the statement is the line a reader would change.

    Evidence
    --------
    Each finding names the importing statement and every private module component or private member
    it reaches. The value reports whether this statement crosses a nonpublic boundary. No automatic
    rename is offered, because the repair may be to expose a public operation, to move the
    implementation, or to drop the dependency entirely.

    Exceptions
    ----------
    A true dunder such as `__version__` is protocol rather than privacy and stays public to this
    rule. A leading-underscore uppercase constant is delegated to `PY-CONS0002`, which owns
    constant placement. External and unresolved imports are excluded, since neither is a boundary
    this repository draws. Git-ignored source never reaches the rule. A framework adapter that has
    to use a documented private API disables the rule at that one boundary rather than renaming
    somebody else's module.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       from ._engine import execute
       from .service import _parse

    Good
    ~~~~
    .. code-block:: python

       from .engine import execute
       from third_party import _documented_adapter
       from .constants import _DEFAULT_TIMEOUT

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "The Python Tutorial", Private Variables
    https://docs.python.org/3/tutorial/classes.html#private-variables
    Cites "The Python Language Reference", the import statement
    https://docs.python.org/3.14/reference/simple_stmts.html#the-import-statement
    """
    frame = subject.lazy(ImportBindingRelation.FACTS)
    boundary = pl.col("has_private_module_component") | (
        pl.col("is_private_member") & ~pl.col("is_private_uppercase_constant")
    )
    value = pl.col("is_project_owned") & boundary
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "project private import"),
    )
