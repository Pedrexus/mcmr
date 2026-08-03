import polars as pl

from ...... import Numeric, rule
from ......facts import ModuleFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-MODU0005", policy=Numeric(maximum=1))
def module_class_count(subject: Table[ModuleFact]) -> CountQuery:
    """Require one primary class at most in each source module.

    Definition
    ----------
    Count classes declared directly at module scope. A source module should normally give one
    primary class a name and a home. A second class usually means that two concepts share one file
    or that a support record has not yet been given a narrower owner.

    Evidence
    --------
    The finding names the module and its exact top-level class count. Nested implementation
    classes do not count. The value is the number of top-level classes.

    Exceptions
    ----------
    Tiny closed type families, generated schemas, and language-mandated companion declarations can
    remain together through an explicit path exclusion. A package initializer should export
    classes from their own modules rather than define the family itself.

    Examples
    --------
    A module defining `Reader` and `Writer` returns `2` and fails the standard ceiling. A module
    defining `Reader` with a nested private cursor returns `1`.

    References
    ----------
    Cites "A Philosophy of Software Design", chapters 4 and 5
    Generalizes wemake-python-styleguide WPS202
    https://wemake-python-styleguide.readthedocs.io/en/latest/pages/usage/violations/complexity.html
    """
    frame = subject.facts().with_columns(pl.col("class_count").alias("value"))
    return count_query(frame, "module class count")
