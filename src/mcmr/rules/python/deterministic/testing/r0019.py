from ..... import rule
from .....facts import TestFunctionFact
from .....models import Count


@rule
def conditional_test_branch_count(
    subject: TestFunctionFact,
) -> Count:
    """Limit conditional branches owned by one collected pytest test.

    Definition
    ----------
    Count `if` statements, conditional expressions, `match` statements, and comprehension filters
    owned directly by each test collected through pytest's default Python conventions. Nested
    functions and classes start independent scopes. Return the branch count for this test. A
    separate policy can compare the value with a project ceiling such as two.

    Evidence
    --------
    Evidence records the complete test range and measured branch count. The metric is syntax based
    and reproducible. It does not ask a model whether a branch is readable. The value is the
    largest branch count any one collected test owns.

    Exceptions
    ----------
    Assertions, exception contexts, and boolean expressions are not control-flow branches under
    this rule. Parametrize input variants instead of selecting expected behavior inside a test.
    Two branches can leave room for bounded invariant checks. A deliberately algorithmic test can
    use a different policy or be omitted by provider selection. The production function
    conditional rule remains separate.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_status(client, authenticated):
           response = client.get("/account")
           if authenticated:
               assert response.status_code == 200
           else:
               assert response.status_code == 401

    Good
    ~~~~
    .. code-block:: python

       @pytest.mark.parametrize(("authenticated", "status"), [(True, 200), (False, 401)])
       def test_status(client, authenticated, status):
           assert client.get("/account").status_code == status

    References
    ----------
    Cites "pytest documentation", parametrization
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    Cites "pytest documentation", anatomy of a test
    https://docs.pytest.org/en/stable/explanation/anatomy.html
    Cites "pytest documentation", default collection conventions
    https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery
    """
    return max(
        (test.owned_conditional_count for test in subject.tests if test.is_collected),
        default=0,
    )
