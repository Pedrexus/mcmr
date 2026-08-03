import polars as pl

from ..... import rule
from .....facts import FunctionFact
from .....query import FindingQuery, RuleQuery
from .....table import FunctionRelation, Table


@rule("PY-DOCU0002")
def tensor_docstring_semantics(subject: Table[FunctionFact]) -> RuleQuery[bool]:
    """Require shape and dtype semantics for public tensor callables.

    Definition
    ----------
    Resolve explicit Torch, CuPy, JAX, torchtyping, and jaxtyping annotations on public module and
    class callables. When at least one parameter or return is a recognized tensor, require both
    shape and dtype semantics in its docstring or structured annotation. Emit one finding per
    callable and identify every tensor role and missing semantic dimension.

    Evidence
    --------
    Each finding covers the callable definition and records tensor parameters or returns together
    with the missing `shape` or `dtype` concepts.

    Exceptions
    ----------
    Private and nested callables, unknown `Tensor` names, and annotations from unrecognized
    libraries are excluded. A nonempty shape string and typed jaxtyping dtype wrapper satisfy the
    corresponding semantics without repeating them in prose.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def normalize(values: torch.Tensor) -> torch.Tensor:
           '''Normalize values.'''

    Good
    ~~~~
    .. code-block:: python

       def normalize(values: torch.Tensor) -> torch.Tensor:
           '''Normalize a float32 tensor with shape `[batch, features]`.'''

    References
    ----------
    Cites "PyTorch documentation", contribution guide, tensor shape and dtype
    https://docs.pytorch.org/docs/stable/community/documentation.html
    Cites "NumPy documentation", array parameters and return values
    https://numpydoc.readthedocs.io/en/latest/format.html
    Cites "jaxtyping documentation", array shape and dtype annotations
    https://docs.kidger.site/jaxtyping/api/array/
    """
    tensor_roles = (
        subject.lazy(FunctionRelation.TENSOR_ROLES)
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("tensor_role_count"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            tensor_roles,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("tensor_role_count").fill_null(0))
    )
    value = (
        (pl.col("visibility") == "public")
        & (pl.col("tensor_role_count") > 0)
        & ~(pl.col("has_tensor_shape_semantics") & pl.col("has_tensor_dtype_semantics"))
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "tensor docstring semantics"),
    )
