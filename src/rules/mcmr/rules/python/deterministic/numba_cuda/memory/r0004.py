import polars as pl

from ...... import rule
from ......facts import CallFact, FunctionFact
from ......query import CountQuery
from ......table import CallRelation, FunctionRelation, Table
from ...gpu_relations import call_rows, counted_calls, numba_kernels


@rule("PY-NUMB0004")
def dynamic_kernel_array_shape(
    subject: Table[CallFact],
    *,
    functions: Table[FunctionFact],
) -> CountQuery:
    """Count local or shared arrays whose shape comes from a kernel parameter.

    Definition
    ----------
    Report `cuda.local.array` and `cuda.shared.array` calls whose shape argument is a parameter of
    the surrounding Numba CUDA kernel. These arrays require a simple compile-time constant shape.
    A launch-time parameter cannot satisfy that contract.

    Evidence
    --------
    Each finding identifies the allocation call, kernel, and dynamic shape parameter. The value is
    the number of kernel arrays with parameter-dependent shapes.

    Exceptions
    ----------
    Literal shapes and names bound to module constants are accepted. Dynamic shared memory passed
    through the launch configuration is a different mechanism and does not call `shared.array`
    with a parameter shape.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       @cuda.jit
       def reduce(values, width):
           tile = cuda.shared.array(width, float32)

    Good
    ~~~~
    .. code-block:: python

       TILE_WIDTH = 256

       @cuda.jit
       def reduce(values):
           tile = cuda.shared.array(TILE_WIDTH, float32)

    References
    ----------
    Cites "Numba CUDA documentation", memory management and local memory
    https://nvidia.github.io/numba-cuda/user/memory.html#local-memory
    Cites "Numba CUDA documentation", CUDA Kernel API and memory management
    https://nvidia.github.io/numba-cuda/reference/kernel.html#memory-management
    """
    kernels = numba_kernels(functions)
    parameters = functions.lazy(FunctionRelation.PARAMETERS).join(
        kernels,
        left_on="function_id",
        right_on="entity_id",
        how="inner",
    )
    shapes = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter((pl.col("root_relation") == "argument") & (pl.col("root_ordinal") == 0))
        .select("call_id", pl.col("text").alias("shape"))
    )
    selected = (
        call_rows(subject)
        .filter(
            pl.col("qualified_name").is_in(["numba.cuda.local.array", "numba.cuda.shared.array"])
        )
        .join(shapes, on="call_id", how="inner")
        .join(parameters, left_on="node_path", right_on="path", how="inner")
        .filter(
            (pl.col("node_start_line") >= pl.col("definition_start_line"))
            & (pl.col("node_end_line") <= pl.col("definition_end_line"))
            & pl.col("shape").str.contains(
                pl.concat_str(pl.lit(r"\b"), pl.col("name"), pl.lit(r"\b"))
            )
        )
    )
    return counted_calls(
        subject,
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualified_name"),
            pl.lit("` takes dynamic kernel parameter `"),
            pl.col("name"),
            pl.lit("` as its shape"),
        ),
        "dynamic kernel array shape",
    )
