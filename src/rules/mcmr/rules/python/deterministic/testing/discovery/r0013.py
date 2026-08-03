from typing import Literal, cast

import polars as pl

from ...... import Category, rule
from ......domain.contracts import Unit
from ......facts import TestSuiteFact
from ......query import FindingQuery, RuleQuery
from ......table import Table
from ..testsuite import TestSuiteTables


@rule("PY-TEST0005", policy=Category(good={"isolated"}, bad={"appended", "prepended", "invalid"}))
def pytest_import_isolation(
    subject: Table[TestSuiteFact],
) -> RuleQuery[Literal["isolated", "appended", "prepended", "invalid"]]:
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
    frame = (
        TestSuiteTables(subject)
        .facts()
        .with_columns(
            pl.when(pl.col("import_mode") == "importlib")
            .then(pl.lit("isolated"))
            .when(pl.col("import_mode") == "append")
            .then(pl.lit("appended"))
            .when(pl.col("import_mode") == "prepend")
            .then(pl.lit("prepended"))
            .otherwise(pl.lit("invalid"))
            .alias("value")
        )
    )
    path_mutating = pl.col("value") != "invalid"
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.lit("`"),
            pl.col("path"),
            pl.lit("` uses pytest import mode `"),
            pl.col("import_mode"),
            pl.lit("`, which "),
            pl.when(path_mutating)
            .then(pl.lit("changes `sys.path` during collection"))
            .otherwise(pl.lit("pytest does not recognize")),
        ),
        (("path-mutating import mode", path_mutating.cast(pl.UInt64), Unit.COUNT),),
        predicate=pl.col("value") != "isolated",
        question=pl.concat_str(
            pl.lit("isolate test imports in `"),
            pl.col("path"),
            pl.lit("`"),
        ),
        options=(
            "set pytest import mode to `importlib`",
            "keep path mutation because tests import sibling test modules",
        ),
        evidence=pl.col("evidence"),
    )
    return cast(
        "RuleQuery[Literal['isolated', 'appended', 'prepended', 'invalid']]",
        RuleQuery.category(
            frame,
            pl.col("value"),
            (pl.col("value") != "isolated").cast(pl.UInt64),
            findings=findings,
        ),
    )
