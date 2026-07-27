from ..... import rule
from .....facts import TestFunctionFact
from .....models import Count


@rule
def direct_shared_test_state_mutation_count(
    subject: TestFunctionFact,
) -> Count:
    """Count direct mutations of module-owned state by collected pytest tests.

    Definition
    ----------
    Inspect functions and methods collected by pytest's default Python conventions. Report direct
    assignment, deletion, augmented assignment, or known mutable-container operations whose root
    name belongs to the test module rather than the test's local scope. An explicit `global`
    assignment is shared state. A fixture parameter or local binding with the same name is local
    and is not reported.

    Evidence
    --------
    Each finding identifies the collected test, mutation site, and shared root. The rule proves a
    direct syntax-level mutation. It does not guess whether an arbitrary called helper has hidden
    side effects. The value is the number of direct mutations of module-owned state.

    Exceptions
    ----------
    Fresh values supplied by function-scoped fixtures are accepted, as are mutations of ordinary
    local variables. Use pytest's `monkeypatch` fixture for process state and yield fixtures for
    state that needs explicit teardown. Ruff's PT family checks fixture syntax, not cross-test
    state ownership.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       REQUESTS = []

       def test_request_is_recorded():
           REQUESTS.append("/health")
           assert REQUESTS == ["/health"]

    Good
    ~~~~
    .. code-block:: python

       @pytest.fixture
       def requests():
           return []

       def test_request_is_recorded(requests):
           requests.append("/health")
           assert requests == ["/health"]

    References
    ----------
    Cites "pytest documentation", fixture reuse and fresh per-test values
    https://docs.pytest.org/en/stable/how-to/fixtures.html#fixtures-are-reusable
    Cites "pytest documentation", monkeypatch guidance
    https://docs.pytest.org/en/stable/how-to/monkeypatch.html
    Cites "pytest documentation", default collection conventions
    https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery
    """
    return sum(test.module_state_mutation_count for test in subject.tests if test.is_collected)
