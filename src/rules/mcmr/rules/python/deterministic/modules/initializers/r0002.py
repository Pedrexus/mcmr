import polars as pl

from ...... import rule
from ......facts import ModuleFact
from ......query import OccurrenceQuery
from ......table import Table
from .....general.deterministic.modules import occurrence_query


@rule("PY-MODU0002")
def empty_package_initializer(subject: Table[ModuleFact]) -> OccurrenceQuery:
    """Report a package initializer that states no executable package surface.

    Definition
    ----------
    Inspect each production Python `__init__.py` after parsing and report it when comments,
    whitespace, and an optional module docstring are its only content. A package initializer should
    state a public surface or be absent so the directory participates as a namespace package.

    Evidence
    --------
    Each finding covers the complete initializer and records its executable statement count. The
    Boolean value is true only when that count is `0`.

    Exceptions
    ----------
    An initializer containing imports, `__all__`, or a supported module customization hook is not
    empty. Test packages are excluded because their package identity can be what makes relative
    fixture and support imports work under the test runner.

    Examples
    --------
    Bad
    ~~~
    An `__init__.py` containing only `\"\"\"Package docs.\"\"\"` returns `true`.

    Good
    ~~~~
    An initializer containing `from .client import Client` returns `false`.

    References
    ----------
    Cites "PEP 420, Implicit Namespace Packages"
    https://peps.python.org/pep-0420/
    Cites "The Python Tutorial", packages
    https://docs.python.org/3.14/tutorial/modules.html#packages
    """
    frame = subject.facts().with_columns(
        (
            pl.col("is_package_initializer")
            & ~pl.col("is_test")
            & (pl.col("executable_statement_count") == 0)
        ).alias("value")
    )
    return occurrence_query(frame, "empty package initializer")
