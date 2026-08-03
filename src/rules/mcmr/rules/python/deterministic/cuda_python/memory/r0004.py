import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-CUDA0004")
def blocking_raw_memory_operation_in_stream_scope(subject: Table[CallFact]) -> CountQuery:
    """Count blocking raw CUDA memory operations in Python stream scopes.

    Definition
    ----------
    Report synchronous allocation, copy, or free calls from `cuda.bindings` in a module that
    creates streams. Stream-ordered buffers and asynchronous copies retain concurrency and express
    ownership more safely through `cuda.core`.

    Evidence
    --------
    Each finding identifies the raw blocking call. The value is the number of blocking memory
    operations in stream-using modules.

    Exceptions
    ----------
    Initialization before any concurrent work and final teardown may be deliberate. A project can
    keep those isolated calls with measured evidence. Asynchronous raw APIs are accepted.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = device.create_stream()
       runtime.cudaMemcpy(target, source, size, kind)

    Good
    ~~~~
    .. code-block:: python

       target.copy_from(source, stream=stream)

    References
    ----------
    Cites "cuda.core documentation", buffer copies and stream-ordered memory
    https://nvidia.github.io/cuda-python/cuda-core/latest/10_minutes_to_cuda_core.html#copying-and-launching
    Cites "cuda.core documentation", Buffer asynchronous release
    https://nvidia.github.io/cuda-python/cuda-core/latest/generated/cuda.core.Buffer.html
    """
    blocking = [
        "cuMemAlloc",
        "cuMemAllocManaged",
        "cuMemAllocPitch",
        "cuMemFree",
        "cuMemFreeHost",
        "cuMemHostAlloc",
        "cuMemcpy",
        "cuMemcpy2D",
        "cuMemcpy3D",
        "cuMemcpyDtoD",
        "cuMemcpyDtoH",
        "cuMemcpyHtoD",
        "cuMemcpyPeer",
        "cudaFree",
        "cudaFreeHost",
        "cudaHostAlloc",
        "cudaMalloc",
        "cudaMalloc3D",
        "cudaMallocHost",
        "cudaMallocManaged",
        "cudaMallocPitch",
        "cudaMemcpy",
        "cudaMemcpy2D",
        "cudaMemcpy3D",
        "cudaMemcpyFromSymbol",
        "cudaMemcpyPeer",
        "cudaMemcpyToSymbol",
        "cudaMemset",
        "cudaMemset2D",
        "cudaMemset3D",
    ]
    calls = call_rows(subject)
    streamed = (
        calls.filter(
            pl.col("qualified_name").str.ends_with(".create_stream")
            | pl.col("qualified_name").str.ends_with(".cudaStreamCreate")
            | pl.col("qualified_name").str.ends_with(".cuStreamCreate")
        )
        .select("fact_id")
        .unique()
    )
    selected = calls.filter(
        pl.col("qualified_name").str.extract(r"([A-Za-z0-9_]+)$", 1).is_in(blocking)
    ).join(streamed, on="fact_id", how="inner")
    return counted_calls(
        subject,
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualified_name"),
            pl.lit("` blocks a Python CUDA stream scope"),
        ),
        "blocking raw memory operation in stream scope",
    )
