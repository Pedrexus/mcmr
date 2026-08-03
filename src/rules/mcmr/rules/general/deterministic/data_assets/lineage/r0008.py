import polars as pl

from ...... import Numeric, rule
from ......facts import DataChangeFact
from ......query import PercentageQuery
from ......table import Table
from ..relations import DataChangeTables, percentage_query


@rule("ALL-DATA0008", policy=Numeric(maximum=5))
def data_change_test_gap_percentage(subject: Table[DataChangeFact]) -> PercentageQuery:
    """Measure impacted downstream assets lacking retained test evidence.

    Definition
    ----------
    Build the impacted set of every breaking change, which is the changed asset together with every
    asset downstream of it, then divide the impacted pairs the change's own test evidence does not
    name by every impacted pair. The result is the share of the blast radius nobody checked, so it
    answers the question a raw impact count leaves open, which is whether anyone looked.

    Test evidence is what the change itself retains rather than what a suite happens to cover,
    because a passing suite that never touches the changed column proves nothing about the change.

    Evidence
    --------
    Each finding names one impacted asset that no retained test evidence covers. The value is the
    percentage of impacted pairs with no test evidence, and it is zero when nothing breaking exists
    to be impacted.

    Exceptions
    ----------
    A nonbreaking change contributes nothing to either side, so a snapshot holding only additive
    changes measures zero rather than a full gap. A snapshot with no breaking change at all
    measures zero for the same reason, since a share of an empty set has no meaning. The changed
    asset counts as impacted by its own change, so covering only its consumers still leaves a gap,
    which is deliberate because the changed asset is the one thing that certainly moved.

    Examples
    --------
    A breaking change to `orders`, whose lineage records `dashboard` and `invoice`, has three
    impacted pairs. Test evidence naming `orders` and `dashboard` leaves one uncovered, so the
    value is about `33.3`. Evidence naming all three returns `0`, and evidence naming none returns
    `100`. A change marked nonbreaking returns `0` whatever its lineage holds.

    References
    ----------
    Cites "The Google Testing Blog", change impact and test selection
    """
    relations = DataChangeTables(subject)
    impacted = relations.impacted()
    tested = relations.tested()
    total = impacted.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("impacted_count")
    )
    uncovered = (
        impacted.join(
            tested,
            on=["fact_id", "asset_identifier", "affected_asset"],
            how="anti",
        )
        .group_by("fact_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("uncovered_count"))
    )
    frame = (
        relations.facts()
        .join(total, on="fact_id", how="left")
        .join(uncovered, on="fact_id", how="left")
        .with_columns(
            pl.col("impacted_count", "uncovered_count").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("impacted_count") == 0)
            .then(0.0)
            .otherwise(pl.col("uncovered_count") / pl.col("impacted_count") * 100.0)
            .alias("value")
        )
    )
    return percentage_query(
        frame,
        "data change test gap percentage",
    )
