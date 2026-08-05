from typing import Literal

import polars as pl

from ...... import rule
from ......facts import DataAssetFact, DataAssetReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import detailed_count_query


@rule("ALL-DATA0013")
def ungoverned_data_reference(
    subject: Table[DataAssetReferenceFact],
    catalog: Table[DataAssetFact],
    *,
    scope: Literal["changed", "all"] = "all",
) -> CountQuery:
    """Count source references to catalog assets that name no owner or no description.

    Definition
    ----------
    Resolve every asset a source location names against the catalog snapshot, read the governance
    that snapshot records for it, and report the reference when the asset names no owner or carries
    no description. This is the pipeline change nobody can review. The code that reads or writes
    the asset is here in the repository with an exact line, while the person who answers for that
    asset and the sentence saying what it holds are both missing from the catalog, so a reviewer
    has no one to ask and no statement of what the numbers mean.

    Where `ALL-DATA0007` measures the catalog and reports the asset, this reports the source
    location that depends on it. The same missing owner is a hygiene item in one place and a
    blocked review in the other, and only the second one points at a file a developer can open.
    The `"changed"` scope narrows the judgment to assets the snapshot marks as changed, which is
    the pipeline edit in front of the reviewer rather than the whole catalog behind it.

    Evidence
    --------
    Each finding records the source location, the asset identifier, and which of ownership and
    description the catalog leaves empty. The value is the number of source references reaching an
    asset with an incomplete governance record.

    Exceptions
    ----------
    A reference the catalog cannot resolve at all is left to `ALL-DATA0001`, so a renamed table is
    never also reported as ungoverned. An asset naming both an owner and a description is never
    reported however stale either one is, since freshness is a different measurement. A description
    of only whitespace reads as absent, because a field holding a space answers nobody. Under
    `scope` `"changed"` an asset the snapshot leaves unmarked is excluded, which is what makes the
    rule adoptable on a catalog that predates it.

    Examples
    --------
    A query reading `warehouse.orders` where the catalog names a domain and no owner returns `1`,
    and a second file reading the same asset returns `1` as well, since the finding is the source
    location. A query reading an asset that names an owner and a description returns `0`.

    References
    ----------
    Cites "DAMA-DMBOK", data governance principles
    Cites "DataHub documentation", ownership and description metadata
    """
    missing_owner = pl.col("missing_owner")
    missing_description = pl.col("missing_description")
    governance = (
        catalog.records("assets")
        .select(
            pl.col("identifier").alias("asset_identifier"),
            (pl.col("owners.length") == 0).alias("missing_owner"),
            (pl.col("description").str.strip_chars() == "").alias("missing_description"),
            "is_changed",
        )
        .unique("asset_identifier", keep="first", maintain_order=True)
    )
    selected = (
        subject.records("references")
        .filter(pl.col("asset_exists"))
        .join(governance, on="asset_identifier", how="inner")
        .filter(
            (pl.lit(scope == "all") | pl.col("is_changed")) & (missing_owner | missing_description)
        )
    )
    return detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("data asset `"),
            pl.col("asset_identifier"),
            pl.lit("` read here has "),
            pl.when(missing_owner & missing_description)
            .then(pl.lit("no owner and no description"))
            .when(missing_owner)
            .then(pl.lit("no owner"))
            .otherwise(pl.lit("no description")),
        ),
        "ungoverned data reference",
    )
