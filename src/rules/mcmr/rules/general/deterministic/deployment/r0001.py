from typing import Literal

import polars as pl

from ..... import Category, rule
from .....facts import DeploymentFact
from .....query import FindingQuery, RuleQuery
from .....table import Table


@rule(
    "ALL-DEPL0001",
    policy=Category(
        good={"reproducible"}, neutral={"not_applicable"}, bad={"partial", "nonreproducible"}
    ),
)
def deployment_reproducibility(
    subject: Table[DeploymentFact], *, require_provenance: bool = True
) -> RuleQuery[Literal["reproducible", "partial", "nonreproducible", "not_applicable"]]:
    """Assess whether deployment can reproduce one known artifact.

    Definition
    ----------
    Read the deployment record and ask whether each artifact that makes a deployment repeatable
    is declared, which are locked inputs, a stated build command, a stated environment, an artifact
    identity, migrations, configuration, a secrets boundary, a rollback path, and provenance when
    `require_provenance` asks for it. All of them present is `reproducible`, some of them is
    `partial`, and none of them is `nonreproducible`.

    The point is not ceremony. A deployment nobody can reproduce is one nobody can roll back to, so
    the moment an incident asks what was actually running, the answer has to be reconstructed from
    memory. A project with no deployment target at all answers `not_applicable`, since a library
    shipped as source has nothing to reproduce.

    Evidence
    --------
    The finding retains every captured input and every step of the deployment the record does not
    cover. The value is the category, one of `reproducible`, `partial`, `nonreproducible`, and
    `not_applicable`.

    Exceptions
    ----------
    A project the record marks as having no deployment target returns `not_applicable` rather than
    failing, so a library is never judged against a service's checklist. Provenance is required
    only when `require_provenance` says so, since a project may attest to its artifacts outside the
    repository. Nothing here inspects a running system, so the rule measures retained deployment
    artifacts rather than the live environment.

    Examples
    --------
    A content-addressed image built from locked inputs, with migrations, configuration, a secrets
    boundary, rollback, and provenance all recorded, returns `reproducible`. The same record
    without rollback returns `partial`. A deployment whose record captures none of the checks, such
    as one performed by editing a live server, returns `nonreproducible`. A library with no
    deployment target returns `not_applicable`.

    References
    ----------
    Cites "Reproducible Builds documentation"
    Cites "SLSA specification"
    Cites "The Twelve-Factor App"
    """
    relations = subject
    checks = [
        pl.col("locked_inputs.length") > 0,
        pl.col("build_command").str.strip_chars() != "",
        pl.col("environment").str.strip_chars() != "",
        pl.col("artifact_identity").str.strip_chars() != "",
        pl.col("migrations.length") > 0,
        pl.col("configuration_sources.length") > 0,
        pl.col("secrets_boundary").str.strip_chars() != "",
        pl.col("rollback_command").str.strip_chars() != "",
    ]
    if require_provenance:
        checks.append(pl.col("provenance").str.strip_chars() != "")
    facts = (
        relations.facts()
        .with_columns(pl.sum_horizontal(*checks).alias("present"))
        .with_columns(
            pl.when(~pl.col("is_applicable"))
            .then(pl.lit("not_applicable"))
            .when(pl.col("present") == len(checks))
            .then(pl.lit("reproducible"))
            .when(pl.col("present") > 0)
            .then(pl.lit("partial"))
            .otherwise(pl.lit("nonreproducible"))
            .alias("value")
        )
    )
    return RuleQuery.category(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_category(
            facts,
            pl.col("value"),
            "deployment reproducibility",
            evidence=pl.col("evidence"),
        ),
    )
