from typing import Literal

import polars as pl

from ...... import rule
from ......facts import DataAssetFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


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
    selected = subject.records("assets").filter(
        (pl.lit(scope == "all") | pl.col("is_changed"))
        & (
            (pl.col("owners.length") == 0)
            | (pl.lit(domain == "required") & (pl.col("domain").str.strip_chars() == ""))
        )
    )
    return count_query(
        subject.counted(selected),
        "data asset governance gap",
    )
