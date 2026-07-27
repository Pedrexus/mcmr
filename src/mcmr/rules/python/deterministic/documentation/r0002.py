from ..... import rule
from .....facts import FunctionFact, Visibility


@rule
def tensor_docstring_semantics(subject: FunctionFact) -> bool:
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
    return (
        subject.visibility is Visibility.PUBLIC
        and bool(subject.recognized_tensor_roles)
        and not (subject.has_tensor_shape_semantics and subject.has_tensor_dtype_semantics)
    )
