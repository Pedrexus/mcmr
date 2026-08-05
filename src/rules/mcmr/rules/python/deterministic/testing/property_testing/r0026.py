import polars as pl

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0018")
def module_generated_parametrization_count(
    subject: Table[TestFunctionFact],
) -> CountQuery:
    """Count parametrizations driven by a module-generated case collection.

    Definition
    ----------
    Find a collected test whose `pytest.mark.parametrize` case source is a module-level list, set,
    or generator comprehension. Unlike a short literal table, its item count grows with repository
    data and silently multiplies the collected suite. Report each generated parametrization once.

    Evidence
    --------
    Each finding points to the test and counts the generated parametrization decorators it carries.
    The value is their sum per module. This rule measures the unbounded collection mechanism rather
    than guessing a case count from source text.

    Exceptions
    ----------
    Literal case tables, static ranges, fixture parametrization, and dynamically returned iterables
    abstain. Keep a generated parametrization only when every case needs its own selection
    identity, marks, retry history, or parallel scheduling. Repository-wide structural invariants
    should normally aggregate their failures inside one test.

    Examples
    --------
    Bad
    ~~~
    Parametrizing one invariant over every discovered `rule module` is reported.

    Good
    ~~~~
    Parametrizing three named `protocol modes` from a literal tuple is not.

    References
    ----------
    Cites "pytest documentation", parametrization
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    Cites "xUnit Test Patterns", test code duplication
    """
    relations = TestFunctionTables(subject)
    selected = relations.collected().filter(pl.col("generated_parametrization_count") > 0)
    return count_query(
        relations.counted(selected, pl.col("generated_parametrization_count")),
        "module generated parametrization count",
    )
