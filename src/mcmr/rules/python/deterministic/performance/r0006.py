from ..... import rule
from .....facts import CallFact
from .....models import Count

_DEVICE_DESTINATIONS = frozenset(
    {
        "cupy.array",
        "cupy.asarray",
        "cupy.from_dlpack",
        "cudf.DataFrame.from_pandas",
        "cudf.Series.from_pandas",
        "torch.as_tensor",
        "torch.from_numpy",
        "torch.tensor",
        "torch.utils.dlpack.from_dlpack",
    }
)
_HOST_BRIDGES = frozenset(
    {
        "cudf.DataFrame.to_pandas",
        "cudf.Series.to_pandas",
        "cupy.asnumpy",
        "cupy.ndarray.get",
        "cupy.ndarray.toDlpack",
        "torch.Tensor.cpu",
        "torch.Tensor.numpy",
        "torch.utils.dlpack.to_dlpack",
    }
)


@rule
def tensor_interoperability_round_trip_count(subject: CallFact) -> Count:
    """Find avoidable host, NumPy, or explicit DLPack tensor round trips.

    Definition
    ----------
    Resolve explicit Torch, CuPy, and RAPIDS import aliases. Report a recognized destination call
    only when its argument syntax proves an intermediate `cpu`, `numpy`, `asnumpy`, `to_pandas`, or
    explicit `to_dlpack` conversion from another supported tensor ecosystem. These libraries expose
    direct CUDA array or DLPack interoperability, so application code should pass the device object
    directly when the installed versions support that contract.

    Evidence
    --------
    Each finding identifies the complete destination call and classifies the unnecessary bridge.
    The value is the number of destination calls fed through an avoidable host bridge.

    Exceptions
    ----------
    Unqualified constructors, unknown aliases, serialization, deliberate host ownership, device
    changes, and a plain `from_dlpack(value)` call are excluded. A boundary may keep an explicit
    bridge when version constraints or lifetime semantics require it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       array = cp.asarray(tensor.cpu().numpy())
       tensor = torch.from_numpy(cp.asnumpy(array))
       array = cp.from_dlpack(torch.utils.dlpack.to_dlpack(tensor))

    Good
    ~~~~
    .. code-block:: python

       array = cp.asarray(tensor)
       tensor = torch.as_tensor(array)

    References
    ----------
    Cites "CuPy documentation", interoperability with PyTorch and the CUDA Array Interface
    https://docs.cupy.dev/en/stable/user_guide/interoperability.html
    Cites "PyTorch documentation", `torch.as_tensor` interoperability
    https://docs.pytorch.org/docs/stable/generated/torch.as_tensor.html
    Cites "cuDF documentation", CuPy interoperability guide
    https://docs.rapids.ai/api/cudf/stable/user_guide/cupy-interop/
    """
    return sum(
        call.qualified_name in _DEVICE_DESTINATIONS
        and not call.is_shadowed
        and any(argument.produced_by(*_HOST_BRIDGES) for argument in call.arguments)
        for call in subject.calls
    )
