import polars as pl

from ...... import rule
from ......facts import DataAssetReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-DATA0001")
def missing_data_asset_reference(subject: Table[DataAssetReferenceFact]) -> CountQuery:
    """Count source references to assets absent from the supplied catalog snapshot.

    Definition
    ----------
    Compare every asset identifier source code names against the identifiers the configured catalog
    snapshot holds, and report each source location whose identifier is absent. A query naming an
    asset nobody catalogs is either a table that was renamed, one that was never created, or one
    this project reads without owning, and all three fail at run time rather than at review.
    Matching is exact, so no fuzzy name resolution and no model opinion changes the answer.

    The catalog is evidence a provider supplies rather than something a parser can derive, since
    the warehouse that holds the asset is outside the repository. A local file, dbt, OpenLineage,
    OpenMetadata, and DataHub all answer the same contract.

    Evidence
    --------
    Each finding records the source path, the line, and the identifier that resolved to nothing.
    The value is the number of source references pointing at an asset the catalog does not hold.

    Exceptions
    ----------
    A reference the catalog does hold is not reported here however unhealthy or deprecated that
    asset is, because lifecycle and quality are what the neighbouring rules answer. An asset a
    query builds by interpolating a name at run time is never an exact identifier, so it is absent
    from the reference stream rather than reported as unresolved. With no catalog snapshot
    configured the rule has nothing to compare against and reports nothing, which is why an empty
    snapshot reads as no findings rather than as every reference failing.

    Examples
    --------
    A query reading `warehouse.orders` where the snapshot holds only `warehouse.customers` returns
    `1`. Two source files reading that same missing asset return `1` each, since the finding is the
    source location rather than the asset. A query reading `warehouse.customers` returns `0`.

    References
    ----------
    Cites "OpenLineage specification", object model and dataset naming specification
    Cites "dbt documentation", manifest and catalog artifacts
    """
    return count_query(
        subject.counted(subject.records("references").filter(~pl.col("asset_exists"))),
        "missing data asset reference",
    )
