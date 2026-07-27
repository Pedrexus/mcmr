from ..... import rule
from .....facts import TestFunctionFact
from .....models import Count


@rule
def unowned_async_test_count(
    subject: TestFunctionFact,
    *,
    anyio_auto: bool = False,
    asyncio_auto: bool = False,
) -> Count:
    """Count async pytest tests without AnyIO or pytest-asyncio ownership.

    Definition
    ----------
    Inspect async functions and methods collected through pytest's default Python conventions.
    Accept a test when its function, class, or module carries `pytest.mark.anyio` or
    `pytest.mark.asyncio`. Also accept direct and transitive requests for AnyIO's `anyio_backend`
    fixture. Set `anyio_auto` or `asyncio_auto` when the matching automatic discovery mode is
    enabled in repository configuration.

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
    accepted_marks = {"pytest.mark.anyio", "pytest.mark.asyncio", "anyio", "asyncio"}
    return sum(
        test.is_async
        and not anyio_auto
        and not asyncio_auto
        and not accepted_marks.intersection(test.marks)
        and "anyio_backend" not in {*test.fixture_names, *test.requested_fixture_names}
        for test in subject.tests
        if test.is_collected
    )
