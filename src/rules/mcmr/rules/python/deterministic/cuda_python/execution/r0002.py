import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import CallRelation, Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-CUDA0002")
def legacy_default_stream_launch(subject: Table[CallFact]) -> CountQuery:
    """Count CUDA core launches submitted to the legacy default stream.

    Definition
    ----------
    Report `cuda.core.launch` when its first argument is `LEGACY_DEFAULT_STREAM`. Work on the
    legacy default stream does not execute concurrently with work on other streams, so one launch
    can serialize an otherwise asynchronous pipeline.

    Evidence
    --------
    Each finding identifies the launch call. The value is the number of launches that explicitly
    select the legacy default stream.

    Exceptions
    ----------
    `PER_THREAD_DEFAULT_STREAM` is accepted because it can overlap nonblocking streams. An owned
    stream created through a device is accepted and remains the clearest contract.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       launch(LEGACY_DEFAULT_STREAM, config, kernel, output)

    Good
    ~~~~
    .. code-block:: python

       stream = device.create_stream()
       launch(stream, config, kernel, output)

    References
    ----------
    Cites "cuda.core documentation", legacy and per-thread default streams
    https://nvidia.github.io/cuda-python/cuda-core/latest/api.html
    Cites "CUDA C++ Programming Guide", default stream behavior
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#default-stream
    """
    first_arguments = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter(
            (pl.col("root_relation") == "argument")
            & (pl.col("root_ordinal") == 0)
            & (pl.col("depth") == 0)
            & (
                pl.col("text").str.ends_with("LEGACY_DEFAULT_STREAM")
                | pl.col("qualified_name").str.ends_with("LEGACY_DEFAULT_STREAM")
            )
        )
        .select("call_id")
    )
    selected = (
        call_rows(subject)
        .filter(pl.col("qualified_name") == "cuda.core.launch")
        .join(first_arguments, on="call_id", how="inner")
    )
    return counted_calls(
        subject,
        selected,
        pl.lit("`cuda.core.launch` submits work to the legacy default stream"),
        "legacy default stream launch",
    )
