from typing import Literal

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import DataAssetFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-DATA0007")
def data_asset_governance_gap(
    subject: Table[DataAssetFact],
    *,
    scope: Literal["changed", "all"] = "changed",
    domain: Literal["required", "optional"] = "required",
) -> CountQuery:
    """Count governed assets missing an owner or required domain.

    Definition
    ----------
    Report each governed asset that names no owner, or that names no domain when `domain` is
    `"required"`. An asset with no owner has nobody to ask when its numbers look wrong and nobody
    to tell when it has to change, and a domain is what says which part of the business its numbers
    are about. Both are cheap to state at creation and expensive to reconstruct years later.

    The `"changed"` scope keeps the default judgment on the assets this change created or modified.
    A project adopting the rule is asked about the work in front of it rather than about its whole
    history. The `"all"` scope measures the entire catalog, which is worth taking as a baseline.

    Evidence
    --------
    Each finding names the asset and the governance fields it leaves empty. The value is the number
    of assets missing an owner or a required domain.

    Exceptions
    ----------
    An unchanged asset is excluded by default, which is what makes the rule adoptable on a catalog
    that predates it. A domain is only required when `domain` is `"required"`, since some catalogs
    model that dimension elsewhere. A whitespace-only domain reads as absent on purpose, because a
    field filled with a space satisfies a schema and answers nobody.

    Examples
    --------
    A newly created asset naming a domain and no owner returns `1`. A changed asset naming both
    returns `0`. An unchanged asset naming neither returns `0` by default and `1` under
    `scope="all"`. With `domain="optional"`, a changed asset naming an owner and no domain returns
    `0`.

    References
    ----------
    Cites "DAMA-DMBOK", data governance principles
    Cites "DataHub documentation", ownership and domain metadata
    """
    missing_owner = pl.col("owners.length") == 0
    missing_domain = pl.lit(domain == "required") & (pl.col("domain").str.strip_chars() == "")
    selected = subject.records("assets").filter(
        (pl.lit(scope == "all") | pl.col("is_changed")) & (missing_owner | missing_domain)
    )
    facts = subject.counted(selected)
    details = selected.join(subject.facts(), on="fact_id", how="left")
    gap_count = missing_owner.cast(pl.UInt64) + missing_domain.cast(pl.UInt64)
    findings = FindingQuery.build(
        details,
        pl.concat_str(
            pl.lit("data asset `"),
            pl.col("identifier"),
            pl.lit("` has "),
            pl.when(missing_owner & missing_domain)
            .then(pl.lit("no owner and no domain"))
            .when(missing_owner)
            .then(pl.lit("no owner"))
            .otherwise(pl.lit("no domain")),
        ),
        (("missing governance fields", gap_count, Unit.COUNT),),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=findings,
    )
