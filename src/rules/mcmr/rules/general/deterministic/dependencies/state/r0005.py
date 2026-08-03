import polars as pl
from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import DependencyFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table


@rule("ALL-DEPE0001", policy=Numeric(minimum=95))
def dependency_technical_lag(
    subject: Table[DependencyFact],
    *,
    maximum_release_lag_days: NonNegativeInt = 180,
    include_development: bool = False,
) -> PercentageQuery:
    """Measure resolved dependencies lagging their latest compatible release.

    Definition
    ----------
    Collect current dependency evidence in memory and compare exact release timestamps. Divide
    in-scope dependencies whose latest compatible release is more than
    `maximum_release_lag_days` newer than the resolved release by all in-scope dependencies with
    complete timestamp evidence.

    Evidence
    --------
    Findings retain the declared requirement, exact resolved and compatible versions, resolved
    version age, release lag, artifact location, and stable evidence identifiers. Missing upstream
    facts remain explicit provider failures and do not become maintenance conclusions. The value is
    the percentage of measurable dependencies lagging past the configured window.

    Exceptions
    ----------
    The comparison uses the latest release compatible with the declared requirement. Local, VCS, or
    otherwise unresolved dependencies remain outside the denominator until evidence is known.
    Package maintenance, archival, and deprecation are separate observations. Development
    dependencies stay out of both sides unless `include_development` asks for them, since a lagging
    test tool and a lagging runtime dependency carry very different risk.

    Examples
    --------
    Four dependencies beyond the configured lag among forty measurable dependencies produce `10`.
    A year-old resolved release matching the latest compatible release does not count as lag.

    References
    ----------
    Cites "PyPI API documentation", release upload timestamps
    https://docs.pypi.org/api/json/
    Cites "Python Packaging User Guide", dependency specification
    https://packaging.python.org/specifications/declaring-project-metadata/
    """
    relations = subject
    complete = relations.records("dependencies").filter(
        (pl.lit(include_development) | ~pl.col("is_development"))
        & pl.col("resolved_release_day").is_not_null()
        & pl.col("latest_compatible_release_day").is_not_null()
    )
    measured = complete.group_by("fact_id", maintain_order=True).agg(
        pl.len().alias("measurable"),
        (
            (pl.col("latest_compatible_release_day") - pl.col("resolved_release_day"))
            > maximum_release_lag_days
        )
        .sum()
        .alias("lagging"),
    )
    facts = (
        relations.facts()
        .join(measured, on="fact_id", how="left")
        .with_columns(
            pl.col("measurable").fill_null(0),
            pl.col("lagging").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("measurable") == 0)
            .then(0.0)
            .otherwise(pl.col("lagging") / pl.col("measurable") * 100.0)
            .alias("value")
        )
    )
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            facts,
            pl.concat_str(
                pl.lit("dependency technical lag is "),
                pl.col("value"),
                pl.lit(" percent for `"),
                pl.col("fact_id"),
                pl.lit("`"),
            ),
            (("dependency technical lag", pl.col("value"), Unit.PERCENTAGE),),
            evidence=pl.col("evidence"),
        ),
    )
