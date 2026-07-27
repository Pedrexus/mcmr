from typing import Literal

from ..... import rule
from .....facts import TestSuiteFact


@rule
def pytest_import_isolation(
    subject: TestSuiteFact,
) -> Literal["isolated", "appended", "prepended", "invalid"]:
    """Classify pytest import isolation from the effective import mode.

    Definition
    ----------
    Read `import_mode` or `--import-mode` from the first pytest configuration selected by pytest.
    `importlib` is isolated because it does not modify `sys.path`. `append` and the default
    `prepend` modes are separate categories because both mutate the import path with different
    precedence. Unknown values are invalid. This project-level check does not overlap Ruff's
    per-statement import rules.

    Evidence
    --------
    Non-isolated and invalid categories retain the effective configuration file and exact mode in
    a finding. Absence is recorded as `prepend`, which is pytest's documented default.

    Exceptions
    ----------
    Tests that intentionally import sibling test modules can accept a path-mutating category.
    Pytest notes that `importlib` prevents test modules from importing one another unless test
    utilities are moved into an importable application package.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: toml

       [tool.pytest.ini_options]
       addopts = "--import-mode=prepend"

    Good
    ~~~~
    .. code-block:: toml

       [tool.pytest]
       import_mode = "importlib"

    References
    ----------
    Cites "pytest documentation", good integration practices
    https://docs.pytest.org/en/stable/explanation/goodpractices.html
    Cites "pytest documentation", import mechanisms
    https://docs.pytest.org/en/stable/explanation/pythonpath.html
    Cites "pytest documentation", configuration precedence
    https://docs.pytest.org/en/stable/reference/customize.html
    """
    match subject.import_mode:
        case "importlib":
            return "isolated"
        case "append":
            return "appended"
        case "prepend":
            return "prepended"
        case _:
            return "invalid"
