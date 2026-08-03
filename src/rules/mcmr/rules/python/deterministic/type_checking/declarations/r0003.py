import polars as pl

from ...... import rule
from ......facts import ProjectConfigurationFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("PY-TYPE0003")
def minimum_python_declaration(
    subject: Table[ProjectConfigurationFact], *, minimum_version: str = "3.14"
) -> CountQuery:
    """Keep project and tool Python targets explicit and mutually consistent.

    Definition
    ----------
    Parse `[project].requires-python` with `packaging`. Require it to exclude every Python 3
    minor below `minimum_version`. When Ruff, Pyrefly, ty, mypy, Pyright, or basedpyright is
    configured, require its target-version key and require that target to equal the minimum
    Python minor admitted by the project declaration. Ruff per-file targets must meet the same
    project minimum because a file cannot safely support less than the published package.

    Evidence
    --------
    Report a missing or invalid `pyproject.toml`, a missing or invalid project declaration, each
    configured tool without an explicit target, and each old or inconsistent target. Locations
    point to the relevant TOML declaration when it can be identified. The value is the number of
    missing or inconsistent Python target declarations.

    Exceptions
    ----------
    A type checker with no `[tool]` table is outside the project and is not required. Interpreter
    discovery is deliberately not accepted for a configured checker because it varies between
    developer machines and CI. Packaging upper bounds and exclusions remain valid when they
    preserve the declared minimum.

    Examples
    --------
    Good
    ~~~~
    `requires-python = ">=3.14"`, Ruff `target-version = "py314"`, and Pyrefly
    `python-version = "3.14"` agree.

    Bad
    ~~~
    `requires-python = ">=3.13"` permits an older interpreter. A configured `[tool.ty]` without
    `[tool.ty.environment].python-version` is missing a stable target. Ruff `py313` disagrees
    with a package whose minimum is Python 3.14.

    References
    ----------
    Cites "Python Packaging User Guide", `requires-python`
    https://packaging.python.org/en/latest/specifications/pyproject-toml/#requires-python
    Cites "packaging documentation", specifier API
    https://packaging.pypa.io/en/stable/specifiers.html
    Cites "Ruff documentation", configuration for `target-version`
    https://docs.astral.sh/ruff/settings/#target-version
    Cites "Pyrefly documentation", `python-version`
    https://pyrefly.org/en/docs/configuration/
    Cites "ty documentation", `python-version`
    https://docs.astral.sh/ty/reference/configuration/#python-version
    """
    try:
        required_minor = int(minimum_version.removeprefix("3."))
    except ValueError:
        raise ValueError(f"Unsupported minimum Python version {minimum_version!r}") from None
    relations = subject
    facts = relations.facts().with_columns(
        pl.col("python_target.project_minimum_minor").alias("admitted")
    )
    targets = relations.values("python_target.tool_target_minors").select(
        "fact_id",
        pl.col("map_key").alias("tool"),
        pl.col("integer_value").alias("target_minor"),
    )
    configured = (
        relations.values("python_target.configured_tools")
        .select("fact_id", pl.col("string_value").alias("tool"))
        .join(targets, on=["fact_id", "tool"], how="left")
        .join(facts.select("fact_id", "admitted"), on="fact_id", how="inner")
        .filter(
            pl.col("target_minor").is_null()
            | (pl.col("admitted").is_not_null() & (pl.col("target_minor") != pl.col("admitted")))
        )
    )
    per_file = (
        relations.values("python_target.per_file_target_minors")
        .join(facts.select("fact_id", "admitted"), on="fact_id", how="inner")
        .filter(pl.col("admitted").is_null() | (pl.col("integer_value") < pl.col("admitted")))
    )
    tool_issues = configured.group_by("fact_id", maintain_order=True).agg(
        pl.len().alias("tool_issues")
    )
    file_issues = per_file.group_by("fact_id", maintain_order=True).agg(
        pl.len().alias("file_issues")
    )
    measured = (
        facts.join(tool_issues, on="fact_id", how="left")
        .join(file_issues, on="fact_id", how="left")
        .with_columns(
            pl.col("tool_issues").fill_null(0),
            pl.col("file_issues").fill_null(0),
        )
        .with_columns(
            (
                pl.col("admitted").is_null().cast(pl.UInt64)
                + (pl.col("admitted") < required_minor).fill_null(False).cast(pl.UInt64)
                + pl.col("tool_issues")
                + pl.col("file_issues")
            ).alias("value")
        )
    )
    return RuleQuery.integer(
        measured,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            measured,
            pl.col("value"),
            "minimum python declaration",
            evidence=pl.col("evidence"),
        ),
    )
