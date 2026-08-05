import polars as pl

from ...... import Numeric, rule
from ......facts import ModuleFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-MODU0002", policy=Numeric(maximum=12))
def module_member_count(
    subject: Table[ModuleFact],
) -> CountQuery:
    """Measure top-level classes and functions as a deterministic focus proxy.

    Definition
    ----------
    Count the synchronous functions, asynchronous functions, and classes one module declares
    directly at module scope, and return their sum. Imported names and nested declarations do not
    count, because the question is how many things this file asks a reader to hold at once rather
    than how many names it can reach.

    The count is a navigation proxy and nothing more. Ten declarations do not mean ten ideas, which
    is why the measurement stops here and a project policy owns the ceiling, and why the contextual
    module-cohesion rule is the one that judges whether the responsibilities actually differ.

    Evidence
    --------
    The finding names the module and its class and function counts separately, so a file wide in
    one and narrow in the other is distinguishable. The value is the number of classes and
    functions the module declares at its own scope.

    Exceptions
    ----------
    A cohesive schema family that outgrows a reasonable ceiling is better answered by becoming a
    package with one model per file and a narrow `__init__.py` export surface than by raising the
    ceiling. A public facade and a compact declarative registry are wide on purpose and are where a
    project raises it instead. wemake-python-styleguide WPS202 offers a stricter default of seven
    combined members, so a project running both should disable one of them.

    Examples
    --------
    A module declaring nine classes and four functions returns `13`. A module declaring eleven
    closely related functions and no class returns `11`. A module that only imports names and
    re-exports them returns `0`, since nothing is declared here.

    References
    ----------
    Generalizes wemake-python-styleguide WPS202
    https://wemake-python-styleguide.readthedocs.io/en/latest/pages/usage/violations/complexity.html
    Cites "Agile Software Development", single responsibility principle
    Cites "A Philosophy of Software Design", chapter 10
    """
    frame = subject.facts().with_columns(
        pl.when(pl.col("is_test"))
        .then(pl.lit(0, dtype=pl.UInt64))
        .otherwise(pl.col("class_count") + pl.col("function_count"))
        .alias("value")
    )
    return count_query(frame, "module member count")
