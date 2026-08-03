import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table

_SYNCHRONOUS_TRANSFERS = {"cudaMemcpy", "cudaMemset", "cudaMemcpy2D", "cudaMemcpy3D"}


@rule("CU-MEMO0001")
def synchronous_transfer_in_stream_scope(subject: Table[CallFact]) -> CountQuery:
    """Count blocking transfers issued where stream work is already in flight.

    Definition
    ----------
    Report a synchronous transfer entry point in a translation unit that also creates or uses a
    non-default stream. A blocking copy synchronizes the whole device with the host, so it drains
    every stream that was overlapping compute with transfer and undoes the reason those streams
    exist. The asynchronous entry point with an explicit stream keeps that overlap.

    Evidence
    --------
    Each finding records the call range, the entry point, and the stream calls that established
    the scope. The value is the number of blocking transfers.

    Exceptions
    ----------
    A translation unit that never touches a stream is left alone, because a blocking copy in a
    purely sequential program costs nothing extra. Setup and teardown transfers outside the hot
    path are legitimate, and a project can narrow this rule to its kernel sources.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       cudaMemcpy(device, host, bytes, cudaMemcpyHostToDevice);

    Good
    ~~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       cudaMemcpyAsync(device, host, bytes, cudaMemcpyHostToDevice, stream);

    References
    ----------
    Cites "CUDA C++ Best Practices Guide", asynchronous transfers and overlapping
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#asynchronous-transfers-and-overlapping-transfers-with-computation
    Cites "CUDA C++ Programming Guide", streams
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#streams
    Cites "The NVIDIA Technical Blog", how to overlap data transfers in CUDA C++
    https://developer.nvidia.com/blog/how-overlap-data-transfers-cuda-cc/
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
    location = (
        pl.when(pl.col("node_end_line") > pl.col("node_start_line"))
        .then(
            pl.concat_str(
                pl.col("node_path"),
                pl.lit(":"),
                pl.col("node_start_line"),
                pl.lit("-"),
                pl.col("node_end_line"),
            )
        )
        .otherwise(pl.concat_str(pl.col("node_path"), pl.lit(":"), pl.col("node_start_line")))
    )
    streams = (
        calls.filter(
            pl.col("qualified_name").is_in(["cudaStreamCreate", "cudaStreamCreateWithFlags"])
        )
        .with_columns(pl.concat_str(pl.lit("`"), location, pl.lit("`")).alias("stream_location"))
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("stream_location").sort_by("ordinal").str.join(", ").alias("stream_locations"))
    )
    selected = calls.filter(pl.col("qualified_name").is_in(_SYNCHRONOUS_TRANSFERS)).join(
        streams, on="fact_id", how="inner"
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            "stream_locations",
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
                pl.lit("` blocks in a scope that creates streams at "),
                pl.col("stream_locations"),
            ),
            (("synchronous transfer in stream scope", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
