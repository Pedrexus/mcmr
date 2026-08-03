import polars as pl

from ...... import rule
from ......facts import CallFact
from ......query import CountQuery
from ......table import CallRelation, Table
from ...gpu_relations import call_rows, counted_calls


@rule("PY-NUMB0005")
def synchronous_transfer_in_numba_stream_scope(subject: Table[CallFact]) -> CountQuery:
    """Count synchronous Numba transfers in modules that create streams.

    Definition
    ----------
    Report `to_device`, `copy_to_device`, or `copy_to_host` without an explicit stream in a module
    that creates a Numba CUDA stream. The default transfer is synchronous and drains the overlap
    the stream was introduced to provide.

    Evidence
    --------
    Each finding identifies the transfer call. The value is the number of synchronous transfers in
    modules that otherwise use streams.

    Exceptions
    ----------
    A module with no stream is left alone. A transfer with a `stream` keyword or a second
    positional argument is accepted. Setup and final result copies outside a hot path may be
    waived with measured evidence.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = cuda.stream()
       device = cuda.to_device(host)

    Good
    ~~~~
    .. code-block:: python

       stream = cuda.stream()
       device = cuda.to_device(host, stream=stream)

    References
    ----------
    Cites "Numba CUDA documentation", memory management and stream-ordered transfers
    https://nvidia.github.io/numba-cuda/reference/memory.html
    Cites "CUDA C++ Best Practices Guide", asynchronous transfers and overlapping
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#asynchronous-transfers-and-overlapping-transfers-with-computation
    """
    calls = call_rows(subject)
    streamed = (
        calls.filter(pl.col("qualified_name") == "numba.cuda.stream").select("fact_id").unique()
    )
    transfers = calls.filter(
        (pl.col("qualified_name") == "numba.cuda.to_device")
        | pl.col("qualified_name").str.ends_with(".copy_to_device")
        | pl.col("qualified_name").str.ends_with(".copy_to_host")
    ).join(streamed, on="fact_id", how="inner")
    positional_streams = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter(
            (pl.col("root_relation") == "argument")
            & (pl.col("depth") == 0)
            & (pl.col("root_ordinal") >= 1)
        )
        .select("call_id")
        .unique()
    )
    keyword_streams = (
        subject.lazy(CallRelation.KEYWORDS)
        .filter(pl.col("name") == "stream")
        .select("call_id")
        .unique()
    )
    selected = transfers.join(positional_streams, on="call_id", how="anti").join(
        keyword_streams, on="call_id", how="anti"
    )
    return counted_calls(
        subject,
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualified_name"),
            pl.lit("` transfers without the module's CUDA stream"),
        ),
        "synchronous transfer in Numba stream scope",
    )
