from ..... import rule
from .....facts import CallFact
from .....models import Count

_WARP_INTRINSICS = frozenset(
    {
        "__syncthreads",
        "__syncwarp",
        "__ballot_sync",
        "__shfl_sync",
        "__shfl_down_sync",
        "__shfl_up_sync",
        "__shfl_xor_sync",
        "__any_sync",
        "__all_sync",
        "__activemask",
    }
)


@rule
def raw_barrier_over_cooperative_groups(subject: CallFact) -> Count:
    """Count raw barriers and warp intrinsics that Cooperative Groups states more safely.

    Definition
    ----------
    Report a call to a raw block barrier or a masked warp intrinsic. Cooperative Groups expresses
    the same synchronization through a typed group object, which makes the scope explicit in the
    signature instead of implicit in a mask argument. A wrong mask is silent, because the threads
    that were left out keep running and the result is a race that reproduces only under some
    occupancy.

    Evidence
    --------
    Each finding records the call range and the intrinsic. The value is the number of raw
    synchronization calls.

    Exceptions
    ----------
    A kernel that must run on a toolkit older than Cooperative Groups keeps the raw form. A
    performance-critical kernel may also keep a hand-written intrinsic after measurement, which is
    a decision worth recording rather than a finding to suppress silently.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: cuda

       __syncthreads();
       value = __shfl_down_sync(0xffffffff, value, offset);

    Good
    ~~~~
    .. code-block:: cuda

       auto block = cooperative_groups::this_thread_block();
       block.sync();
       auto warp = cooperative_groups::tiled_partition<32>(block);
       value = warp.shfl_down(value, offset);

    References
    ----------
    Cites "CUDA C++ Programming Guide", Cooperative Groups
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#cooperative-groups
    Cites "The NVIDIA Technical Blog", Cooperative Groups, flexible CUDA thread programming
    https://developer.nvidia.com/blog/cooperative-groups/
    Cites "CUDA C++ Programming Guide", warp shuffle functions
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#warp-shuffle-functions
    """
    return sum(call.qualified_name in _WARP_INTRINSICS for call in subject.calls)
