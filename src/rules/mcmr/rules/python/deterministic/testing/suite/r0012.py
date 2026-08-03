from typing import Literal, cast

import polars as pl

from ...... import Category, rule
from ......domain.contracts import Unit
from ......facts import TestSuiteFact
from ......query import FindingQuery, RuleQuery
from ......table import Table
from ..testsuite import TestSuiteTables


@rule("PY-TEST0004", policy=Category(good={"strict"}, bad={"partial", "permissive"}))
def pytest_configuration_strictness(
    subject: Table[TestSuiteFact],
) -> RuleQuery[Literal["strict", "partial", "permissive"]]:
    """Classify whether pytest rejects configuration and marker mistakes.

    Definition
    ----------
    Read the first pytest configuration selected by pytest's documented file precedence. Classify
    the project as `strict` when `strict = true`, `--strict`, or all four Pytest 9 controls are
    enabled. These are `strict_config`, `strict_markers`, `strict_parametrization_ids`, and
    `strict_xfail`. Classify any incomplete nonempty subset as `partial` and no enabled controls as
    `permissive`. Explicit individual values override global strict mode. The corresponding flags
    in `addopts` count when pytest provides one. This complements Ruff's PT rules because it checks
    project policy rather than Python test syntax.

    Evidence
    --------
    The finding names the configuration file the suite is read from, every strictness control
    that is off, and how many of them are on out of how many there are. The repair is a choice,
    since a suite is tightened one control at a time. The category is derived only from parsed
    configuration and never from a model opinion.

    Exceptions
    ----------
    A project that intentionally accepts dynamically registered third-party markers can configure
    `partial` as acceptable. Environment-only `PYTEST_ADDOPTS` is not assumed because it is not a
    reproducible repository setting.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: toml

       [tool.pytest.ini_options]
       addopts = "-q"

    Good
    ~~~~
    .. code-block:: toml

       [tool.pytest]
       strict = true

    References
    ----------
    Cites "pytest documentation", configuration reference
    https://docs.pytest.org/en/stable/reference/customize.html
    Cites "pytest documentation", strict configuration options
    https://docs.pytest.org/en/stable/reference/reference.html#configuration-options
    Cites "Ruff documentation", pytest-style rules
    https://docs.astral.sh/ruff/rules/#flake8-pytest-style-pt
    """
    controls = [
        "strict_config",
        "strict_markers",
        "strict_parametrization_ids",
        "strict_xfail",
    ]
    relations = TestSuiteTables(subject)
    facts = relations.facts()
    enabled = (
        relations.values("strict_controls")
        .filter(pl.col("map_key").is_in(controls) & pl.col("boolean_value"))
        .select("fact_id", "map_key")
    )
    missing = (
        facts.select("fact_id")
        .join(pl.DataFrame({"map_key": controls}).lazy(), how="cross")
        .join(enabled, on=["fact_id", "map_key"], how="anti")
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("map_key").sort().alias("missing"))
    )
    frame = (
        facts.join(missing, on="fact_id", how="left")
        .with_columns(pl.col("missing").fill_null(pl.lit([], dtype=pl.List(pl.String))))
        .with_columns((pl.lit(len(controls)) - pl.col("missing").list.len()).alias("enabled"))
        .with_columns(
            pl.when(pl.col("enabled") == len(controls))
            .then(pl.lit("strict"))
            .when(pl.col("enabled") > 0)
            .then(pl.lit("partial"))
            .otherwise(pl.lit("permissive"))
            .alias("value")
        )
    )
    enabled_phrase = (
        pl.when(pl.col("enabled") == 1)
        .then(pl.lit("1 strictness control"))
        .otherwise(pl.concat_str(pl.col("enabled"), pl.lit(" strictness controls")))
    )
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.lit("`"),
            pl.col("path"),
            pl.lit("` turns on "),
            enabled_phrase,
            pl.lit(f" of the {len(controls)} there are, leaving `"),
            pl.col("missing").list.join("`, `"),
            pl.lit("` off"),
        ),
        (
            ("controls turned on", pl.col("enabled"), Unit.COUNT),
            ("controls there are", pl.lit(len(controls)), Unit.COUNT),
        ),
        predicate=pl.col("value") != "strict",
        question=pl.concat_str(
            pl.lit("turn on `"),
            pl.col("missing").list.first(),
            pl.lit("` in `"),
            pl.col("path"),
            pl.lit("`"),
        ),
        options=(
            "enable them one at a time and repair what each one exposes",
            "state the whole strict mode and take the failures at once",
        ),
        evidence=pl.col("evidence"),
    )
    return cast(
        "RuleQuery[Literal['strict', 'partial', 'permissive']]",
        RuleQuery.category(
            frame,
            pl.col("value"),
            (pl.col("value") != "strict").cast(pl.UInt64),
            findings=findings,
        ),
    )
