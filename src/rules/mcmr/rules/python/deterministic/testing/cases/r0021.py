import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import TestCaseGroupFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from .case_relations import TestCaseTables


@rule("PY-TEST0013")
def manual_literal_test_case_loop_count(
    subject: Table[TestCaseGroupFact],
    *,
    minimum_cases: NonNegativeInt = 3,
) -> CountQuery:
    """Count manual literal case loops that should use Pytest parametrization.

    Definition
    ----------
    Inspect tests collected by Pytest's default Python conventions. Report a `for` loop when it
    iterates over at least `minimum_cases` literal list, tuple, or set entries and owns an
    assertion. The default requires three cases. Parametrization gives each case an independent
    collection identity, failure report, mark surface, and selection target.

    Evidence
    --------
    Each finding identifies the test and loop range and records the number of manual cases. The
    rule does not rewrite case IDs or infer fixture parameters. The value is the number of manual
    literal case loops.

    Exceptions
    ----------
    Dynamic iterables, loops without assertions, and fewer than three cases abstain. Keep a loop
    when iteration order or accumulated state is the behavior under test. Use Hypothesis instead
    when the cases represent a broad generated domain rather than a short example table.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_normalize():
           for raw in ("A", "B", "C"):
               assert normalize(raw).islower()

    Good
    ~~~~
    .. code-block:: python

       @pytest.mark.parametrize("raw", ["A", "B", "C"])
       def test_normalize(raw):
           assert normalize(raw).islower()

    References
    ----------
    Cites "pytest documentation", parametrization
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    """
    relations = TestCaseTables(subject)
    selected = relations.loops().filter(
        (pl.col("case_count") >= minimum_cases) & pl.col("owns_assertion")
    )
    frame = relations.counted(selected)
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        pl.lit(1, dtype=pl.UInt64),
        findings=FindingQuery.precise_integer(
            frame,
            value,
            "manual literal test case loop count",
            evidence=pl.col("evidence"),
        ),
    )
