import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table

_WARP_INTRINSICS = {
    "__syncthreads",
    "__syncwarp",
    "__ballot_sync",
    "__shfl_sync",
    "__shfl_down_sync",
    "__shfl_up_sync",
    "__shfl_xor_sync",
    "__any_sync",
    "__all_sync",
    "__activemask",
}


@rule("CU-LAUN0001")
def raw_barrier_over_cooperative_groups(subject: Table[CallFact]) -> CountQuery:
    """Count raw barriers and warp intrinsics that Cooperative Groups states more safely.

    Definition
    ----------
    Report a call to a raw block barrier or a masked warp intrinsic. Cooperative Groups expresses
    the same synchronization through a typed group object, which makes the scope explicit in the
    signature instead of implicit in a mask argument. A wrong mask is silent, because the threads
    that were left out keep running and the result is a race that reproduces only under some
    occupancy.

    Evidence
    --------
    Each finding records the call range and the intrinsic. The value is the number of raw
    synchronization calls.

    Exceptions
    ----------
    A kernel that must run on a toolkit older than Cooperative Groups keeps the raw form. A
    performance-critical kernel may also keep a hand-written intrinsic after measurement, which is
    a decision worth recording rather than a finding to suppress silently.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: cuda

       __syncthreads();
       value = __shfl_down_sync(0xffffffff, value, offset);

    Good
    ~~~~
    .. code-block:: cuda

       auto block = cooperative_groups::this_thread_block();
       block.sync();
       auto warp = cooperative_groups::tiled_partition<32>(block);
       value = warp.shfl_down(value, offset);

    References
    ----------
    Cites "CUDA C++ Programming Guide", Cooperative Groups
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#cooperative-groups
    Cites "The NVIDIA Technical Blog", Cooperative Groups, flexible CUDA thread programming
    https://developer.nvidia.com/blog/cooperative-groups/
    Cites "CUDA C++ Programming Guide", warp shuffle functions
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#warp-shuffle-functions
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    calls = subject.lazy(CallRelation.CALLS).join(
        facts.select("fact_id"), on="fact_id", how="inner"
    )
    selected = calls.filter(pl.col("qualified_name").is_in(_WARP_INTRINSICS))
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("qualified_name"),
                pl.lit("` uses a raw CUDA synchronization intrinsic"),
            ),
            (("raw barrier over cooperative groups", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
