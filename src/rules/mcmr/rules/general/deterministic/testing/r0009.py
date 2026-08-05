import polars as pl

from ..... import Numeric, rule
from .....facts import ModuleFact
from .....query import CountQuery
from .....table import Table
from ..modules.relations import count_query


@rule("ALL-TEST0003", policy=Numeric(maximum=20))
def test_module_member_count(
    subject: Table[ModuleFact],
) -> CountQuery:
    """Measure top-level test helpers, classes, and tests as one suite navigation width.

    Definition
    ----------
    Count classes and functions declared directly in a test module. This separates production
    module focus from suite navigation while keeping a strict ceiling on scenario sprawl. The
    default allows twenty members, compared with twelve for production modules.

    Evidence
    --------
    Each finding names the test module and its exact top-level member count. The value sums its
    classes, helpers, and tests rather than the number of parametrized items Pytest collects.

    Exceptions
    ----------
    Nested declarations and imported helpers do not count. Parametrized cases remain one member and
    are governed by the dedicated testing rules. A cohesive suite above the ceiling should first
    remove duplicate intent, aggregate repository-wide invariants, or split by production behavior.

    Examples
    --------
    A file with eighteen tests and two helpers returns `20`. A file with twenty-one distinct tests
    returns `21` even if every test is short.

    References
    ----------
    Cites "xUnit Test Patterns", organizing test code
    Cites "Growing Object-Oriented Software, Guided by Tests", expressive test suites
    """
    frame = subject.facts().with_columns(
        pl.when(pl.col("is_test"))
        .then(pl.col("class_count") + pl.col("function_count"))
        .otherwise(pl.lit(0, dtype=pl.UInt64))
        .alias("value")
    )
    return count_query(frame, "test module member count")
