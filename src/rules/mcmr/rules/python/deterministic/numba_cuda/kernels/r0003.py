import polars as pl

from ...... import rule
from ......facts import FunctionFact, SyntaxFact
from ......query import CountQuery
from ......table import SyntaxRelation, Table
from ...gpu_relations import counted_syntax, numba_kernels


@rule("PY-NUMB0003")
def unguarded_grid_index(
    subject: Table[SyntaxFact],
    *,
    functions: Table[FunctionFact],
) -> CountQuery:
    """Count Numba grid indices never bounded by a branch or grid-stride loop.

    Definition
    ----------
    Report a value assigned from `cuda.grid()` when no branch or loop in the kernel reads that
    value. Launch grids normally round up to a whole block, so the extra threads need a bounds
    check or a grid-stride loop before indexing an array.

    Evidence
    --------
    Each finding identifies the grid index assignment and kernel. The value is the number of grid
    indices that never participate in bounded control flow.

    Exceptions
    ----------
    A kernel intentionally launched over an exact multiple may be safe, but that launch contract
    is not local to the kernel. A project can retain it with an explicit waiver. A grid index read
    by any branch or loop is accepted without guessing the comparison operator.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       position = cuda.grid(1)
       output[position] = input[position]

    Good
    ~~~~
    .. code-block:: python

       position = cuda.grid(1)
       if position < output.size:
           output[position] = input[position]

    References
    ----------
    Cites "Numba CUDA documentation", writing CUDA kernels and absolute positions
    https://nvidia.github.io/numba-cuda/user/kernels.html#absolute-positions
    Cites "Numba CUDA documentation", CUDA Kernel API and `forall`
    https://nvidia.github.io/numba-cuda/reference/kernel.html#numba.cuda.compiler.Dispatcher.forall
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    kernel_facts = facts.join(
        numba_kernels(functions),
        left_on=["path", "qualname"],
        right_on=["path", "name"],
        how="inner",
    ).select("fact_id", "qualname")
    nodes = subject.lazy(SyntaxRelation.NODES)
    children = subject.lazy(SyntaxRelation.CHILDREN)
    grids = nodes.filter(
        (pl.col("kind") == "call") & pl.col("name").str.ends_with(".grid")
    ).select(
        "fact_id",
        pl.col("ordinal").alias("grid_ordinal"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    )
    bindings = nodes.filter(pl.col("kind") == "binding").select(
        "fact_id",
        pl.col("ordinal").alias("binding_ordinal"),
        pl.col("name").alias("index_name"),
    )
    indexed = grids.join(
        children.select(
            "fact_id",
            pl.col("parent_ordinal").alias("binding_ordinal"),
            pl.col("child_ordinal").alias("grid_ordinal"),
        ),
        on=["fact_id", "grid_ordinal"],
        how="inner",
    ).join(bindings, on=["fact_id", "binding_ordinal"], how="inner")
    controls = nodes.filter(pl.col("kind").is_in(["branch", "loop"])).select(
        "fact_id",
        pl.col("ordinal").alias("control_ordinal"),
        "subtree_end",
    )
    names = nodes.filter(pl.col("kind") == "name").select(
        "fact_id",
        pl.col("ordinal").alias("name_ordinal"),
        pl.col("name").alias("used_name"),
    )
    guarded = (
        indexed.select("fact_id", "grid_ordinal", "index_name")
        .join(controls, on="fact_id", how="inner")
        .join(names, on="fact_id", how="inner")
        .filter(
            (pl.col("used_name") == pl.col("index_name"))
            & (pl.col("control_ordinal") < pl.col("name_ordinal"))
            & (pl.col("name_ordinal") < pl.col("subtree_end"))
        )
        .select("fact_id", "grid_ordinal")
        .unique()
    )
    selected = (
        indexed.join(guarded, on=["fact_id", "grid_ordinal"], how="anti")
        .rename({"grid_ordinal": "ordinal"})
        .join(kernel_facts, on="fact_id", how="inner")
    )
    return counted_syntax(
        subject,
        selected,
        pl.concat_str(
            pl.lit("Numba CUDA grid index `"),
            pl.col("index_name"),
            pl.lit("` is never bounded by control flow in `"),
            pl.col("qualname"),
            pl.lit("`"),
        ),
        "unguarded grid index",
    )
