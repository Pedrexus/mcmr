import polars as pl

from ...... import rule
from ......facts import DataAssetReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import detailed_count_query


@rule("ALL-DATA0006")
def unhealthy_data_dependency(subject: Table[DataAssetReferenceFact]) -> CountQuery:
    """Count source references exposed to explicitly unhealthy data dependencies.

    Definition
    ----------
    For each resolved source reference, read the health the provider recorded for every asset
    upstream of the one this code reads, and count each pair of a source reference and an unhealthy
    upstream asset once. Code that reads a healthy table fed by a broken one is producing wrong
    answers with no error anywhere, which is the failure mode a schema check cannot see and a
    freshness alert on the wrong asset will not raise.

    Unknown health stays unknown. An asset nobody measured is not evidence of a problem, and
    treating it as one would make the count grow with the size of the lineage graph rather than
    with the number of real failures.

    Evidence
    --------
    Each finding names the source reference and the upstream asset whose retained quality evidence
    failed. The value is the number of source reference and unhealthy upstream pairs.

    Exceptions
    ----------
    An upstream asset marked `healthy` or `unknown` is never counted, so a lineage graph with no
    quality evidence at all reports nothing rather than everything. A reference whose own asset the
    catalog does not hold is skipped, since `ALL-DATA0001` owns it and its upstream lineage is
    unknowable. One unhealthy asset feeding four source references is reported four times on
    purpose, because each of those four places is a separate reader producing a wrong answer.

    Examples
    --------
    A source reference whose upstream map records one asset `unhealthy` and another `unknown`
    returns `1`. Two source references reading that same asset return `1` each. A reference whose
    upstream assets are all `healthy` or all `unknown` returns `0`.

    References
    ----------
    Cites "OpenLineage specification", lineage model
    Cites "DAMA-DMBOK", data quality dimensions
    """
    selected = (
        subject.values("references.upstream_health")
        .filter(pl.col("string_value") == "unhealthy")
        .join(
            subject.records("references")
            .filter(pl.col("asset_exists"))
            .select("fact_id", "record_id", "asset_identifier"),
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "record_id"],
            how="inner",
        )
    )
    return detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("data asset `"),
            pl.col("asset_identifier"),
            pl.lit("` depends on unhealthy upstream asset `"),
            pl.col("map_key"),
            pl.lit("`"),
        ),
        "unhealthy data dependency",
    )
