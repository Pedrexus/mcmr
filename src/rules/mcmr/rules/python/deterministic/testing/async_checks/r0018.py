from typing import Literal

import polars as pl

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0010")
def unowned_async_test_count(
    subject: Table[TestFunctionFact],
    *,
    discovery: Literal["explicit", "automatic"] = "explicit",
) -> CountQuery:
    """Count async pytest tests without AnyIO or pytest-asyncio ownership.

    Definition
    ----------
    Inspect async functions and methods collected through pytest's default Python conventions.
    Accept a test when its function, class, or module carries `pytest.mark.anyio` or
    `pytest.mark.asyncio`. Also accept direct and transitive requests for AnyIO's `anyio_backend`
    fixture. Set `discovery` to `"automatic"` when an async plugin automatically owns every async
    test in repository configuration.

    Evidence
    --------
    Each finding identifies one async test for which no supported runner contract is visible.
    Fixture ownership follows statically declared fixture dependencies to a fixed point. Dynamic
    plugin hooks are not guessed. The value is the number of async tests with no visible runner
    contract.

    Exceptions
    ----------
    A project with a custom async collector can exclude its paths. Strict pytest-asyncio mode
    requires an asyncio marker. AnyIO accepts its marker, automatic mode, or a direct or indirect
    `anyio_backend` request. Ruff PT rules do not prove async-plugin ownership.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       async def test_fetch():
           assert (await fetch()).status == 200

    Good
    ~~~~
    .. code-block:: python

       pytestmark = pytest.mark.anyio

       async def test_fetch():
           assert (await fetch()).status == 200

    References
    ----------
    Cites "AnyIO documentation", asynchronous test ownership
    https://anyio.readthedocs.io/en/stable/testing.html#creating-asynchronous-tests
    Cites "pytest-asyncio documentation", strict and auto discovery
    https://pytest-asyncio.readthedocs.io/en/stable/concepts.html#test-discovery-modes
    Cites "pytest documentation", default collection conventions
    https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery
    """
    relations = TestFunctionTables(subject)
    accepted_marks = relations.values("tests.marks").filter(
        pl.col("string_value").is_in(
            ["pytest.mark.anyio", "pytest.mark.asyncio", "anyio", "asyncio"]
        )
    )
    backend_fixtures = pl.concat(
        [
            relations.values("tests.fixture_names"),
            relations.values("tests.requested_fixture_names"),
        ]
    ).filter(pl.col("string_value") == "anyio_backend")
    owned = pl.concat(
        [
            accepted_marks.select("fact_id", "parent_id"),
            backend_fixtures.select("fact_id", "parent_id"),
        ]
    ).unique()
    unowned = (
        relations.collected()
        .filter(pl.col("is_async") & pl.lit(discovery == "explicit"))
        .join(
            owned,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="anti",
        )
    )
    return count_query(relations.counted(unowned), "unowned async test count")
