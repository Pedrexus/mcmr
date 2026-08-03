from ...... import Numeric, rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0012", policy=Numeric(maximum=10))
def owned_test_statement_count(
    subject: Table[TestFunctionFact],
) -> CountQuery:
    """Limit executable statements owned by one collected pytest test.

    Definition
    ----------
    Count every AST statement owned by each function or method collected through pytest's default
    Python conventions. Statements nested under local control flow count because they remain part
    of the test. A nested function or class counts as one declaration while its body starts an
    independent scope. Ignore the test docstring and return this test's statement count. A
    separate policy can compare the value with a project ceiling such as 25.

    Evidence
    --------
    Evidence records the test range and exact statement count. A default policy can define an
    explicit maintainability budget rather than claiming that pytest defines a limit. The value is
    the largest statement count any one collected test owns.

    Exceptions
    ----------
    End-to-end tests can configure a larger budget when one behavior genuinely needs a long
    scenario. Prefer fixtures for reusable setup and parametrization for repeated cases. Do not
    extract a single-use helper merely to satisfy the number because that hides the test's
    algorithm without reducing it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_checkout(client):
           # More than 25 separate setup, action, and assertion statements.
           ...

    Good
    ~~~~
    .. code-block:: python

       def test_checkout(configured_cart, client):
           response = client.post("/checkout", json=configured_cart)
           assert response.status_code == 201
           assert response.json()["state"] == "paid"

    References
    ----------
    Cites "pytest documentation", anatomy of a test
    https://docs.pytest.org/en/stable/explanation/anatomy.html
    Cites "pytest documentation", fixtures
    https://docs.pytest.org/en/stable/how-to/fixtures.html
    Cites "pytest documentation", parametrization
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    """
    return count_query(
        TestFunctionTables(subject).collected_maximum("owned_statement_count"),
        "owned test statement count",
    )
