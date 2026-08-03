import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-NUMB0007")
def device_wide_numba_synchronization_in_stream_scope(
    subject: Table[CallFact],
) -> CountQuery:
    """Count device-wide Numba synchronization in modules that create streams.

    Definition
    ----------
    Report `cuda.synchronize()` in a module that creates a Numba CUDA stream. The call waits for
    all work on the device, including independent work on other streams. Synchronize the stream or
    an event that represents the actual dependency instead.

    Evidence
    --------
    Each finding identifies the device-wide wait. The value is the number of global Numba waits in
    modules that otherwise use streams.

    Exceptions
    ----------
    An explicit benchmark boundary or process shutdown may need a device-wide wait. Retain such a
    call only with a project waiver that states the measured boundary.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = cuda.stream()
       cuda.synchronize()

    Good
    ~~~~
    .. code-block:: python

       stream = cuda.stream()
       stream.synchronize()

    References
    ----------
    Cites "Numba CUDA documentation", CUDA Kernel API and synchronization
    https://nvidia.github.io/numba-cuda/reference/kernel.html#synchronization-and-atomic-operations
    Cites "CUDA C++ Programming Guide", explicit synchronization
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#explicit-synchronization
    """
    calls = call_rows(subject)
    streamed = (
        calls.filter(pl.col("qualified_name") == "numba.cuda.stream").select("fact_id").unique()
    )
    selected = calls.filter(pl.col("qualified_name") == "numba.cuda.synchronize").join(
        streamed, on="fact_id", how="inner"
    )
    return counted_calls(
        subject,
        selected,
        pl.lit("`numba.cuda.synchronize` waits for every CUDA stream"),
        "device-wide Numba synchronization in stream scope",
    )
