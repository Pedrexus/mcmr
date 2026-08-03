import polars as pl
from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import ArchitectureCharacteristicFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table


@rule("ALL-ARCH0001", policy=Numeric(minimum=95))
def architecture_fitness_coverage(
    subject: Table[ArchitectureCharacteristicFact],
    *,
    require_ci: bool = True,
    maximum_age_days: NonNegativeInt = 30,
) -> PercentageQuery:
    """Measure declared architecture characteristics with executable fitness evidence.

    Definition
    ----------
    Divide declared architecture characteristics protected by an objective, executable check,
    retained result, current observation date, owner, and scope by all declared characteristics.
    The result must come from CI when configured. Documentation or tool presence alone does not
    count as executable coverage.

    Evidence
    --------
    Findings link each quality characteristic to its objective, check, retained evidence, scope,
    owner, observation date, and CI or repeatable review path. The value is the percentage of
    declared characteristics carrying current executable evidence.

    Exceptions
    ----------
    Characteristics that cannot be automated may use a declared repeatable review with retained
    evidence when project policy permits it. A result older than `maximum_age_days` no longer
    counts as coverage, since a fitness function nobody has run recently is documentation. Setting
    `require_ci` to false accepts a check a person runs on demand, which is what a project without
    continuous integration has to do.

    Examples
    --------
    Eight of ten declared characteristics with current retained checks produce `80`. A written
    latency goal with no recent retained result does not count.

    References
    ----------
    Cites "Building Evolutionary Architectures", Fitness Functions
    Cites "Architecture Tradeoff Analysis Method"
    Cites "ISO IEC IEEE 42010", architecture descriptions
    """
    relations = subject
    characteristics = relations.records("characteristics")
    verification = pl.col("verification")
    verified = (verification == "ci") | (verification == "repeatable_review")
    if not require_ci:
        verified |= verification == "manual"
    complete = pl.all_horizontal(
        pl.col("objective").str.strip_chars() != "",
        pl.col("check").str.strip_chars() != "",
        pl.col("retained_result").str.strip_chars() != "",
        pl.col("owner").str.strip_chars() != "",
        pl.col("scope").str.strip_chars() != "",
        pl.col("observation_age_days") <= maximum_age_days,
        verified,
    )
    facts = relations.coverage(characteristics, complete.fill_null(False))
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "architecture fitness coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
