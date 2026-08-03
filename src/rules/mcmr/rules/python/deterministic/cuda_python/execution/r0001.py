import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-CUDA0001")
def direct_cuda_core_lifecycle_construction(subject: Table[CallFact]) -> CountQuery:
    """Count direct construction of CUDA core stream and context wrappers.

    Definition
    ----------
    Report direct calls to `cuda.core.Stream` or `cuda.core.Context`. Their constructors are not a
    supported ownership boundary. Streams come from `Device.create_stream`, and contexts come from
    a device or stream that already owns the correct CUDA context.

    Evidence
    --------
    Each finding identifies the direct constructor call. The value is the number of unsupported
    stream or context constructions.

    Exceptions
    ----------
    `Stream.from_handle` is accepted because it explicitly borrows or wraps an existing stream.
    `Device.create_stream` is accepted because the device establishes ownership and context.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = Stream()

    Good
    ~~~~
    .. code-block:: python

       device = Device()
       stream = device.create_stream()

    References
    ----------
    Cites "cuda.core documentation", Stream construction
    https://nvidia.github.io/cuda-python/cuda-core/latest/generated/cuda.core.Stream.html
    Cites "cuda.core documentation", Context construction
    https://nvidia.github.io/cuda-python/cuda-core/latest/generated/cuda.core.Context.html
    """
    selected = call_rows(subject).filter(
        pl.col("qualified_name").is_in(["cuda.core.Context", "cuda.core.Stream"])
    )
    return counted_calls(
        subject,
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualified_name"),
            pl.lit("` is constructed directly instead of through its owner"),
        ),
        "direct CUDA core lifecycle construction",
    )
