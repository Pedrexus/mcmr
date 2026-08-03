import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....facts import ExceptionFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("PY-EXCE0003")
def shared_exception_placement(
    subject: Table[ExceptionFact],
    *,
    minimum_importing_modules: NonNegativeInt = 2,
    preferred_module: str = "exceptions",
) -> CountQuery:
    """Place reused exception classes in the narrowest justified `exceptions.py`.

    Definition
    ----------
    Resolve the top-level project classes derived directly or transitively from `BaseException`,
    `Exception`, or an error-named base, match the explicit project `from` imports that reach them,
    and report an exception at least `minimum_importing_modules` distinct ordinary modules import
    while its defining module is not already named `preferred_module`. An exception several modules
    import is a shared contract, and leaving it in the module that happens to raise it makes every
    consumer depend on that module for a name rather than for behavior.

    A relative import is resolved against the package of the module that wrote it, so the same
    `from .service import OrderError` line in two packages names two different definitions and
    each is counted against the one it reaches.

    Evidence
    --------
    Each finding names the exception, the dotted module that defines it, and every ordinary module
    that imports it by name. The value is the number of exceptions reused widely enough to move.

    Exceptions
    ----------
    A file-local exception and one only a single module imports are excluded, since neither is a
    shared contract yet. A package `__init__.py` re-export, an import-only re-export module, a star
    import, a dynamic import, and module-qualified attribute access are not counted as consumers,
    because none of them proves that a second module depends on the name. An exception already
    living in a module named `preferred_module` is stable and not reported again. Keeping a domain
    exception beside its sole owner is right whenever moving it would weaken cohesion or introduce
    an import cycle.

    Examples
    --------
    An `OrderConflictError` defined in `orders/service.py` and imported independently by
    `orders/api.py` and `orders/jobs.py` returns `1`, since two ordinary modules depend on the
    name. The same class living in `orders/exceptions.py` returns `0`. A `LocalParseError` raised
    and caught only inside `parser.py` returns `0`, and so does one that a single module imports
    and one that only the package initializer hands on.

    References
    ----------
    Cites "The Python Tutorial", user-defined exceptions
    https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions
    Cites "The Python Language Reference", import system
    https://docs.python.org/3/reference/import.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    relations = subject
    imports = (
        relations.values("exceptions.importing_modules")
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(pl.col("string_value").n_unique().alias("importing_modules"))
    )
    selected = (
        relations.records("exceptions")
        .join(
            imports,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .with_columns(pl.col("importing_modules").fill_null(0))
        .filter(
            (pl.col("importing_modules") >= minimum_importing_modules)
            & ~pl.col("defining_module").str.ends_with(f".{preferred_module}")
        )
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "shared exception placement",
            evidence=pl.col("evidence"),
        ),
    )
