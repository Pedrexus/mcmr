from ..... import rule
from .....facts import ImportBindingFact


@rule
def conftest_import(
    subject: ImportBindingFact,
    *,
    allowed_modules: tuple[str, ...] = (),
) -> bool:
    """Detect an explicit import of a pytest `conftest` module.

    Definition
    ----------
    Inspect Python import statements for `import conftest`, `from conftest import fixture`,
    package-qualified imports such as `from tests.conftest import client`, and relative forms such
    as `from . import conftest`. The expected default is zero because pytest discovers fixtures and
    local plugins from `conftest.py` according to directory scope.

    Evidence
    --------
    Each finding identifies the complete import statement and every conftest module it names.
    A statement is counted once even when it binds several names from the same module.

    Exceptions
    ----------
    `allowed_modules` can exempt an exact, uniquely packaged compatibility module when an external
    integration requires a normal import. Pytest discovery remains preferred. Imports from ordinary
    fixture plugin modules are accepted and are the supported way to share fixtures without
    broadening a conftest boundary. Ruff's pytest rules do not own conftest imports.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       from tests.conftest import authenticated_client

       def test_account(authenticated_client):
           assert authenticated_client.get("/account").status_code == 200

    Good
    ~~~~
    .. code-block:: python

       def test_account(authenticated_client):
           assert authenticated_client.get("/account").status_code == 200

    References
    ----------
    Cites "pytest documentation", writing plugins and conftest.py plugins
    https://docs.pytest.org/en/stable/how-to/writing_plugins.html#conftest-py-local-per-directory-plugins
    Cites "pytest documentation", fixture availability
    https://docs.pytest.org/en/stable/reference/fixtures.html#fixture-availability
    """
    imports_conftest = "conftest" in {
        subject.name,
        subject.imported_name,
        *subject.module.split("."),
    }
    return imports_conftest and subject.module not in allowed_modules
