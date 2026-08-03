import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0014")
def finite_range_hypothesis_candidate_count(
    subject: Table[TestFunctionFact],
    *,
    minimum_cases: NonNegativeInt = 10,
) -> CountQuery:
    """Count broad integer ranges that should use a Hypothesis strategy.

    Definition
    ----------
    Inspect tests collected by Pytest's default Python conventions. Report
    `pytest.mark.parametrize` when its values are a static `range` containing at least
    `minimum_cases` integers. The default is ten. A long contiguous domain is generation, not a
    short example table, and Hypothesis can explore it while shrinking a failure to a minimal
    counterexample.

    Evidence
    --------
    Each finding identifies the decorated test and records the exact finite range size. The rule
    does not claim that every short example table should use property-based testing. The value is
    the number of broad finite ranges a strategy would state better.

    Exceptions
    ----------
    Dynamic ranges, noninteger case sources, short curated boundary tables, and already generated
    strategies abstain. Keep parametrization when every value has distinct domain meaning or
    needs an explicit case ID or mark. A Hypothesis test still needs a stated invariant.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       @pytest.mark.parametrize("value", range(100))
       def test_round_trip(value):
           assert decode(encode(value)) == value

    Good
    ~~~~
    .. code-block:: python

       @given(st.integers(min_value=0, max_value=99))
       def test_round_trip(value):
           assert decode(encode(value)) == value

    References
    ----------
    Cites "Hypothesis documentation", introduction and when to use property-based testing
    https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html#when-to-use-hypothesis-and-property-based-testing
    Cites "Hypothesis documentation", quickstart
    https://hypothesis.readthedocs.io/en/latest/quickstart.html
    """
    relations = TestFunctionTables(subject)
    collected = relations.collected().select("fact_id", "record_id")
    candidates = (
        relations.values("tests.parametrized_range_sizes")
        .filter(pl.col("integer_value") >= minimum_cases)
        .join(
            collected,
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "record_id"],
            how="inner",
        )
    )
    return count_query(
        relations.counted(candidates),
        "finite range hypothesis candidate count",
    )
