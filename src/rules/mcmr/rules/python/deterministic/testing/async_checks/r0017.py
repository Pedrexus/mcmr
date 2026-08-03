import polars as pl

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0009")
def synchronous_test_asyncio_run_count(
    subject: Table[TestFunctionFact],
) -> CountQuery:
    """Count `asyncio.run` calls owned by synchronous pytest tests.

    Definition
    ----------
    Resolve ordinary and aliased imports of `asyncio.run` in modules matching pytest's default
    collection conventions. Report each direct call owned by a synchronous collected test. Calls
    inside a nested helper scope are independent and are not attributed to the test.

    Evidence
    --------
    Each finding identifies the collected test and exact runner call. The rule does not match an
    unrelated local function named `run` or a same-named parameter that shadows an import. The
    value is the number of runner calls owned by a synchronous collected test.

    Exceptions
    ----------
    `asyncio.run` remains appropriate at an application entry point. In pytest, prefer an async
    test owned by AnyIO or pytest-asyncio so the plugin controls event-loop isolation, fixtures,
    cancellation, and cleanup. Ruff's PT rules do not check event-loop ownership.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_fetch():
           response = asyncio.run(fetch())
           assert response.status == 200

    Good
    ~~~~
    .. code-block:: python

       @pytest.mark.anyio
       async def test_fetch():
           response = await fetch()
           assert response.status == 200

    References
    ----------
    Cites "The Python Standard Library", asyncio runners
    https://docs.python.org/3/library/asyncio-runner.html#running-an-asyncio-program
    Cites "AnyIO documentation", asynchronous tests
    https://anyio.readthedocs.io/en/stable/testing.html#creating-asynchronous-tests
    Cites "pytest-asyncio documentation", test discovery modes
    https://pytest-asyncio.readthedocs.io/en/stable/concepts.html#test-discovery-modes
    """
    relations = TestFunctionTables(subject)
    synchronous_tests = (
        relations.collected().filter(~pl.col("is_async")).select("fact_id", "record_id")
    )
    calls = (
        relations.calls()
        .filter(pl.col("qualified_name") == "asyncio.run")
        .join(
            synchronous_tests,
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "record_id"],
            how="inner",
        )
    )
    return count_query(
        relations.counted(calls),
        "synchronous test asyncio run count",
    )
