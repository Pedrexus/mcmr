import polars as pl

from ...... import rule
from ......facts import CallFact, FunctionFact, SyntaxFact
from ......query import CountQuery
from ......table import SyntaxRelation, Table
from ...gpu_relations import call_rows, counted_syntax, numba_kernels


@rule("PY-NUMB0006")
def default_stream_numba_kernel_launch(
    subject: Table[SyntaxFact],
    *,
    calls: Table[CallFact],
    functions: Table[FunctionFact],
) -> CountQuery:
    """Count Numba kernel launches that omit a stream where streams exist.

    Definition
    ----------
    Report a Numba dispatcher launch whose configuration supplies only grid and block in a Python
    module that creates a CUDA stream. Numba's third launch item is the stream, so omitting it
    sends the kernel to the default stream and can serialize otherwise concurrent work.

    Evidence
    --------
    Each finding identifies the launch and owning function. The value is the number of launches
    with fewer than three top-level configuration items in a stream-using module.

    Exceptions
    ----------
    A module that creates no stream has no local overlap to drain. An explicit third configuration
    item is accepted. Nested tuples used for multidimensional grids count as one item because the
    syntax tree retains the top-level configuration shape.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       stream = cuda.stream()
       scale[grid, block](values)

    Good
    ~~~~
    .. code-block:: python

       stream = cuda.stream()
       scale[grid, block, stream](values)

    References
    ----------
    Cites "Numba CUDA documentation", CUDA Kernel API and launch configuration
    https://nvidia.github.io/numba-cuda/reference/kernel.html#kernel-declaration
    Cites "CUDA C++ Programming Guide", default stream behavior
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#default-stream
    """
    stream_paths = (
        call_rows(calls)
        .filter(pl.col("qualified_name") == "numba.cuda.stream")
        .select(pl.col("node_path").alias("path"))
        .unique()
    )
    facts = subject.lazy(SyntaxRelation.FACTS).join(stream_paths, on="path", how="inner")
    nodes = subject.lazy(SyntaxRelation.NODES)
    children = subject.lazy(SyntaxRelation.CHILDREN)
    call_nodes = nodes.filter(pl.col("kind") == "call").select(
        "fact_id",
        pl.col("ordinal").alias("call_ordinal"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    )
    indices = nodes.filter(pl.col("kind") == "index").select(
        "fact_id", pl.col("ordinal").alias("index_ordinal")
    )
    collections = nodes.filter(pl.col("kind") == "collection").select(
        "fact_id", pl.col("ordinal").alias("collection_ordinal")
    )
    call_indices = children.filter(pl.col("child_order") == 0).select(
        "fact_id",
        pl.col("parent_ordinal").alias("call_ordinal"),
        pl.col("child_ordinal").alias("index_ordinal"),
    )
    index_children = children.select(
        "fact_id",
        pl.col("parent_ordinal").alias("index_ordinal"),
        pl.col("child_ordinal").alias("collection_ordinal"),
    )
    configurations = (
        call_nodes.join(call_indices, on=["fact_id", "call_ordinal"], how="inner")
        .join(indices, on=["fact_id", "index_ordinal"], how="inner")
        .join(index_children, on=["fact_id", "index_ordinal"], how="inner")
        .join(collections, on=["fact_id", "collection_ordinal"], how="inner")
    )
    indexed_kernels = (
        index_children.join(
            nodes.filter(pl.col("kind") == "name").select(
                "fact_id",
                pl.col("ordinal").alias("collection_ordinal"),
                pl.col("name").alias("kernel_name"),
            ),
            on=["fact_id", "collection_ordinal"],
            how="inner",
        )
        .select("fact_id", "index_ordinal", "kernel_name")
        .join(
            numba_kernels(functions).select("path", pl.col("name").alias("kernel_name")),
            on="kernel_name",
            how="inner",
        )
    )
    item_counts = children.group_by("fact_id", "parent_ordinal", maintain_order=True).agg(
        pl.len().alias("configuration_items")
    )
    selected = (
        configurations.join(
            indexed_kernels,
            on=["fact_id", "index_ordinal", "path"],
            how="inner",
        )
        .join(
            item_counts,
            left_on=["fact_id", "collection_ordinal"],
            right_on=["fact_id", "parent_ordinal"],
            how="inner",
        )
        .filter(pl.col("configuration_items") < 3)
        .rename({"call_ordinal": "ordinal"})
        .join(facts.select("fact_id", "qualname"), on="fact_id", how="inner")
    )
    return counted_syntax(
        subject,
        selected,
        pl.concat_str(
            pl.lit("Numba kernel launch in `"),
            pl.col("qualname"),
            pl.lit("` omits the CUDA stream"),
        ),
        "default stream Numba kernel launch",
    )
