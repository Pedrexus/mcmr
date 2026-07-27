from ..... import rule
from .....facts import CallFact
from .....models import Count

_SYNCHRONOUS_TRANSFERS = frozenset({"cudaMemcpy", "cudaMemset", "cudaMemcpy2D", "cudaMemcpy3D"})


@rule
def synchronous_transfer_in_stream_scope(subject: CallFact) -> Count:
    """Count blocking transfers issued where stream work is already in flight.

    Definition
    ----------
    Report a synchronous transfer entry point in a translation unit that also creates or uses a
    non-default stream. A blocking copy synchronizes the whole device with the host, so it drains
    every stream that was overlapping compute with transfer and undoes the reason those streams
    exist. The asynchronous entry point with an explicit stream keeps that overlap.

    Evidence
    --------
    Each finding records the call range, the entry point, and the stream calls that established
    the scope. The value is the number of blocking transfers.

    Exceptions
    ----------
    A translation unit that never touches a stream is left alone, because a blocking copy in a
    purely sequential program costs nothing extra. Setup and teardown transfers outside the hot
    path are legitimate, and a project can narrow this rule to its kernel sources.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       cudaMemcpy(device, host, bytes, cudaMemcpyHostToDevice);

    Good
    ~~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       cudaMemcpyAsync(device, host, bytes, cudaMemcpyHostToDevice, stream);

    References
    ----------
    Cites "CUDA C++ Best Practices Guide", asynchronous transfers and overlapping
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#asynchronous-transfers-and-overlapping-transfers-with-computation
    Cites "CUDA C++ Programming Guide", streams
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#streams
    Cites "The NVIDIA Technical Blog", how to overlap data transfers in CUDA C++
    https://developer.nvidia.com/blog/how-overlap-data-transfers-cuda-cc/
    """
    if not subject.count_calls("cudaStreamCreate", "cudaStreamCreateWithFlags"):
        return 0
    return sum(call.qualified_name in _SYNCHRONOUS_TRANSFERS for call in subject.calls)
