import polars as pl

from ...... import Numeric, rule
from ......facts import ModuleFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-MODU0006", policy=Numeric(maximum=200))
def module_statement_count(subject: Table[ModuleFact]) -> CountQuery:
    """Limit the total statement inventory one source module owns.

    Definition
    ----------
    Count statements throughout the module, including statements nested inside classes,
    functions, and control-flow blocks. Declarations count because they also ask a reader to
    understand one source-level decision. Comments and blank lines do not count.

    Evidence
    --------
    The finding names the module and its exact recursive statement count. The value is the number
    of statements owned by that file.

    Exceptions
    ----------
    Generated parsers, schemas, and migration snapshots can be excluded by path. Hand-written
    modules should split at a coherent responsibility boundary instead of raising the ceiling.

    Examples
    --------
    A file with 150 statements across ten functions returns `150`. A file with 201 returns `201`
    and fails the standard ceiling even when no individual function is long.

    References
    ----------
    Generalizes Ruff PLR0915 too-many-statements
    https://docs.astral.sh/ruff/rules/too-many-statements/
    Cites "Clean Code", chapter 10, Classes
    """
    frame = subject.facts().with_columns(pl.col("statement_count").alias("value"))
    return count_query(frame, "module statement count")
