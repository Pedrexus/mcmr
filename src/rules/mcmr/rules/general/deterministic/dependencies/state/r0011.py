import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import DependencyFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table


@rule("ALL-DEPE0004", policy=Numeric(maximum=5))
def dependency_evidence_gap_percentage(subject: Table[DependencyFact]) -> PercentageQuery:
    """Measure dependencies missing facts required by offline version checks.

    Definition
    ----------
    Collect current dependency evidence in memory and divide records missing an exact resolved
    release date, latest compatible version, or latest compatible release date by all records.
    The selected provider, not a bundled package catalog, defines the target project's evidence.

    Evidence
    --------
    Every finding identifies the dependency, resolved version, missing fields, artifact source
    location, and any bounded collection failures on the record. The percentage is zero for
    an empty dependency set because there is no missing package evidence to measure. The value is
    the percentage of dependency records missing a required fact.

    Exceptions
    ----------
    Local, VCS, private-index, and ambiguous environment resolutions can remain unknown, but their
    missing facts stay visible rather than being guessed. Projects may ignore this rule when an
    internal evidence provider owns those packages. This rule does not judge package quality,
    capability fit, or maintenance.

    Examples
    --------
    Two incomplete records among ten dependencies return `20`. Complete evidence returns `0`.
    A network failure records the missing fields and failure source in the current check.

    References
    ----------
    Cites "Python Packaging User Guide", Simple Repository API
    https://packaging.python.org/en/latest/specifications/simple-repository-api/
    Cites "PyPI API documentation", exact release metadata
    https://docs.pypi.org/api/json/
    Cites "Python Packaging User Guide", lock file specification
    https://packaging.python.org/en/latest/specifications/pylock-toml/
    """
    relations = subject
    incomplete = relations.records("dependencies").filter(
        pl.col("resolved_release_day").is_null()
        | pl.col("latest_compatible_version").is_null()
        | pl.col("latest_compatible_release_day").is_null()
    )
    counts = incomplete.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("incomplete")
    )
    facts = (
        relations.facts()
        .join(counts, on="fact_id", how="left")
        .with_columns(pl.col("incomplete").fill_null(0))
        .with_columns(
            pl.when(pl.col("dependencies.length") == 0)
            .then(0.0)
            .otherwise(pl.col("incomplete") / pl.col("dependencies.length") * 100.0)
            .alias("value")
        )
    )
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            facts,
            pl.concat_str(
                pl.lit("dependency evidence gap percentage is "),
                pl.col("value"),
                pl.lit(" for `"),
                pl.col("fact_id"),
                pl.lit("`"),
            ),
            (("dependency evidence gap percentage", pl.col("value"), Unit.PERCENTAGE),),
            evidence=pl.col("evidence"),
        ),
    )
