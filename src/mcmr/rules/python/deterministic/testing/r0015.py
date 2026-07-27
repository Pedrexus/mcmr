from ..... import rule
from .....facts import TestSuiteFact


@rule
def coverage_without_branch_measurement(subject: TestSuiteFact) -> bool:
    """Detect configured coverage that measures statements without branches.

    Definition
    ----------
    Return true when Coverage.py or pytest-cov is configured but branch measurement is not
    enabled. Resolve `.coveragerc`, `.coveragerc.toml`, `setup.cfg`, `tox.ini`, and
    `pyproject.toml` using Coverage.py's documented precedence. A repository `--cov-config`
    override is honored. `branch = true` in the effective run section or `--cov-branch` in pytest
    `addopts` satisfies the rule. Coverage-free projects abstain with false.

    Evidence
    --------
    The finding identifies the selected coverage or pytest configuration file and records that
    statement coverage is configured without branch arcs. The result never guesses from a report
    percentage.

    Exceptions
    ----------
    A project that intentionally measures only statements can disable this rule explicitly.
    Environment variables and CI-only flags are not assumed unless they are represented in a
    repository configuration file.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: toml

       [tool.coverage.run]
       source = ["package"]

    Good
    ~~~~
    .. code-block:: toml

       [tool.coverage.run]
       source = ["package"]
       branch = true

    References
    ----------
    Cites "Coverage.py documentation", configuration reference
    https://coverage.readthedocs.io/en/latest/config.html
    Cites "Coverage.py documentation", branch coverage
    https://coverage.readthedocs.io/en/latest/branch.html
    Cites "pytest-cov documentation", configuration
    https://pytest-cov.readthedocs.io/en/latest/config.html
    """
    return subject.is_coverage_configured and not subject.is_branch_coverage_enabled
