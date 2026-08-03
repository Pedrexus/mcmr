import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-CUDA0003")
def device_wide_synchronization_in_stream_scope(subject: Table[CallFact]) -> CountQuery:
    """Count device-wide synchronization where a Python CUDA module uses streams.

    Definition
    ----------
    Report `cudaDeviceSynchronize` or `cuCtxSynchronize` in a module that creates a CUDA stream.
    Device-wide synchronization waits for unrelated work on every stream. Prefer stream or event
    synchronization that states the dependency actually required.

    Evidence
    --------
    Each finding identifies the global synchronization call. The value is the number of global
    waits in stream-using modules.

    Exceptions
    ----------
    Process shutdown and explicit benchmark barriers may require a device-wide wait. Those call
    sites should retain measured intent in a project waiver rather than making global waits the
    default coordination primitive.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = device.create_stream()
       runtime.cudaDeviceSynchronize()

    Good
    ~~~~
    .. code-block:: python

       stream = device.create_stream()
       stream.sync()

    References
    ----------
    Cites "cuda.bindings documentation", runtime execution control
    https://nvidia.github.io/cuda-python/cuda-bindings/latest/module/runtime.html
    Cites "cuda.core documentation", streams and event management
    https://nvidia.github.io/cuda-python/cuda-core/latest/generated/cuda.core.Stream.html
    """
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
        pl.col("qualified_name").str.ends_with(".cudaDeviceSynchronize")
        | pl.col("qualified_name").str.ends_with(".cuCtxSynchronize")
    ).join(streamed, on="fact_id", how="inner")
    return counted_calls(
        subject,
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualified_name"),
            pl.lit("` waits for every CUDA stream"),
        ),
        "device-wide synchronization in stream scope",
    )
