import polars as pl

from ...... import rule
from ......facts import FunctionFact, SyntaxFact
from ......query import CountQuery
from ......table import SyntaxRelation, Table
from ...gpu_relations import counted_syntax, numba_kernels


@rule("PY-NUMB0002")
def conditional_block_barrier(
    subject: Table[SyntaxFact],
    *,
    functions: Table[FunctionFact],
) -> CountQuery:
    """Count Numba block barriers reached through divergent control flow.

    Definition
    ----------
    Report `cuda.syncthreads()` inside a branch or loop in a Numba CUDA kernel. A block barrier is
    valid only when every thread in the block reaches it. Thread-dependent control flow can leave
    part of the block waiting forever or produce undefined behavior.

    Evidence
    --------
    Each finding identifies the barrier and its kernel. The value is the number of block barriers
    nested in conditional or iterative control flow.

    Exceptions
    ----------
    Uniform conditions proven from block-invariant values may be safe, but the syntax alone cannot
    prove that uniformity. Keep such a barrier only with an explicit project waiver and evidence.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       if cuda.threadIdx.x < active:
           cuda.syncthreads()

    Good
    ~~~~
    .. code-block:: python

       value = tile[cuda.threadIdx.x] if cuda.threadIdx.x < active else 0
       cuda.syncthreads()

    References
    ----------
    Cites "Numba CUDA documentation", CUDA Kernel API and synchronization
    https://nvidia.github.io/numba-cuda/reference/kernel.html#synchronization-and-atomic-operations
    Cites "CUDA C++ Programming Guide", synchronization functions
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#synchronization-functions
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    kernel_facts = facts.join(
        numba_kernels(functions),
        left_on=["path", "qualname"],
        right_on=["path", "name"],
        how="inner",
    ).select("fact_id", "qualname")
    nodes = subject.lazy(SyntaxRelation.NODES)
    barriers = nodes.filter(
        (pl.col("kind") == "call") & pl.col("name").str.ends_with(".syncthreads")
    ).select(
        "fact_id",
        pl.col("ordinal").alias("barrier_ordinal"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    )
    control = nodes.filter(pl.col("kind").is_in(["branch", "loop"])).select(
        "fact_id",
        pl.col("ordinal").alias("control_ordinal"),
        "subtree_end",
    )
    selected = (
        barriers.join(control, on="fact_id", how="inner")
        .filter(
            (pl.col("control_ordinal") < pl.col("barrier_ordinal"))
            & (pl.col("barrier_ordinal") < pl.col("subtree_end"))
        )
        .unique(["fact_id", "barrier_ordinal"], maintain_order=True)
        .rename({"barrier_ordinal": "ordinal"})
        .join(kernel_facts, on="fact_id", how="inner")
    )
    return counted_syntax(
        subject,
        selected,
        pl.concat_str(
            pl.lit("Numba CUDA kernel `"),
            pl.col("qualname"),
            pl.lit("` reaches a block barrier conditionally"),
        ),
        "conditional block barrier",
    )
