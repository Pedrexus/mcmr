import polars as pl

from ..... import rule
from .....facts import ModuleFact
from .....query import OccurrenceQuery
from .....table import Table
from ....general.deterministic.modules import occurrence_query


@rule("PY-MODU0001")
def non_init_reexport_module(subject: Table[ModuleFact]) -> OccurrenceQuery:
    """Find barrel modules that define no behavior beyond re-exporting imports.

    Definition
    ----------
    Report an ordinary Python file when its complete executable body contains only imports and an
    `__all__` assignment. Package `__init__.py` files are the explicit export boundary. A module
    named `models.py`, `types.py`, or any other name must define the concept its name promises
    instead of forwarding unrelated definitions.

    Evidence
    --------
    The finding cites every import line and the full barrel module range. Modules with a class,
    function, constant, registration call, or other executable statement are not classified as
    pure re-export barrels.

    Exceptions
    ----------
    Package initializers are always excluded. A compatibility facade may disable the rule while a
    migration is active, though compatibility-only modules should not remain by default in a new
    project.

    Examples
    --------
    Bad
    ~~~
    `models.py` imports `User`, `Finding`, and `Status` from other modules and lists them in
    `__all__` without defining a model.

    Good
    ~~~~
    `models/__init__.py` exports shared model classes defined one per sibling file. Internal code
    may also import the defining modules directly when no public package surface is needed.

    References
    ----------
    Cites "The Python Language Reference", packages and package initialization
    https://docs.python.org/3/tutorial/modules.html#packages
    Cites "The Python Language Reference", `__all__` reference
    https://docs.python.org/3/reference/simple_stmts.html#the-import-statement
    Cites "A Philosophy of Software Design", chapters 4 and 7
    """
    frame = subject.facts().with_columns(
        (
            pl.col("has_only_imports_and_all")
            & ~pl.col("is_package_initializer")
            & ~pl.col("path").str.ends_with("conftest.py")
        ).alias("value")
    )
    return occurrence_query(frame, "non init reexport module")
