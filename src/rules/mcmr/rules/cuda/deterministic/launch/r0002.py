import polars as pl

from ..... import rule
from .....facts import KernelLaunchFact
from .....query import FindingQuery, OccurrenceQuery, RuleQuery
from .....table import Table


@rule("CU-LAUN0002")
def default_stream_kernel_launch(subject: Table[KernelLaunchFact]) -> OccurrenceQuery:
    """Detect one kernel launch that names no stream and therefore takes the default one.

    Definition
    ----------
    Read the execution configuration a launch states and report one whose fourth argument is
    absent or is the null stream, in a translation unit that takes part in stream work at all. A
    launch with no stream runs on the legacy default stream, which synchronizes implicitly against
    every other stream on the device, so one such launch in the middle of an overlapped pipeline
    drains the overlap the rest of the code was built to get. The cost does not show up in the
    launch itself. It shows up as the copies and kernels around it losing their concurrency, which
    is why reading it here is worth more than profiling for it later.

    Evidence
    --------
    Each finding names the kernel, the grid and block it launches with, and the function that
    launches it. The Boolean result reports whether this launch takes the default stream where
    another stream exists to be drained.

    Exceptions
    ----------
    A translation unit that neither creates a stream nor is handed one has nothing to serialize
    against, so its launches are not reported. Being handed a stream counts as much as creating
    one, since a function that receives a `cudaStream_t` and launches without it drains exactly the
    overlap its caller set up. Setup or teardown outside the hot path costs nothing extra either. A
    project compiled with per-thread default streams gets a different default whose behavior is the
    opposite, so it turns this rule off rather than threading a stream it does not need.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       scale<<<grid, block>>>(data);

    Good
    ~~~~
    .. code-block:: cuda

       cudaStreamCreate(&stream);
       scale<<<grid, block, 0, stream>>>(data);

    A file that names no stream anywhere returns `False` for `scale<<<grid, block>>>(data)`,
    because nothing it can reach was overlapping in the first place.

    References
    ----------
    Cites "CUDA C++ Programming Guide", streams and the default stream
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#default-stream
    Cites "The NVIDIA Technical Blog", GPU pro tip, CUDA 7 streams simplify concurrency
    https://developer.nvidia.com/blog/gpu-pro-tip-cuda-7-streams-simplify-concurrency/
    Cites "CUDA C++ Best Practices Guide", concurrent kernel execution
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#concurrent-kernel-execution
    """
    frame = subject.facts()
    value = pl.col("unit_uses_streams") & pl.col("stream").is_in(
        ["", "0", "NULL", "nullptr", "cudaStreamDefault"]
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame,
            value,
            "default stream kernel launch",
            evidence=pl.col("evidence"),
        ),
    )
