import polars as pl

from ...... import rule
from ......facts import DataAssetReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-DATA0004")
def nonactive_data_asset_reference(subject: Table[DataAssetReferenceFact]) -> CountQuery:
    """Count source references to assets explicitly deprecated or removed.

    Definition
    ----------
    Report each source reference whose resolved asset carries a `deprecated` or `removed` lifecycle
    in the catalog. Somebody published that state on purpose to say the asset is going away, and
    every reference still pointing at it is work the migration has not reached. Reading it is what
    turns a planned removal into an incident.

    Only a declared state counts. Age, low usage, and absent metadata are guesses about intent, so
    an asset nobody has touched in two years stays active until a person says otherwise.

    Evidence
    --------
    Each finding records the source location, the asset identifier, and the exact lifecycle state
    the catalog declares. The value is the number of references pointing at a deprecated or removed
    asset.

    Exceptions
    ----------
    An asset whose lifecycle is `active` or `unknown` is never reported, because an unset field is
    missing evidence rather than a declared retirement. A reference to an asset the catalog does
    not hold at all belongs to `ALL-DATA0001` and is skipped here. A reference kept deliberately
    during a migration is still reported, since the count is what says how much of the migration is
    left, and a project that wants it silenced excludes the path rather than the state.

    Examples
    --------
    A reference to an asset the catalog marks `deprecated` returns `1`, and so does one marked
    `removed`. A reference to an active asset created three years ago returns `0`, because age is
    not a lifecycle. A reference to an asset carrying no lifecycle at all also returns `0`.

    References
    ----------
    Cites "Data Contract Specification", lifecycle management
    Cites "DataHub documentation", dataset deprecation metadata
    """
    selected = subject.records("references").filter(
        pl.col("asset_exists") & pl.col("lifecycle").is_in(["deprecated", "removed"])
    )
    return count_query(
        subject.counted(selected),
        "nonactive data asset reference",
    )
