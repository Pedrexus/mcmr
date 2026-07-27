from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import OperationFact


class BoundedWork(StrEnum):
    BOUNDED = auto()
    UNBOUNDED = auto()
    BACKPRESSURED = auto()
    DROPPED = auto()
    UNCERTAIN = auto()


@rule
async def bounded_work(
    subject: OperationFact,
    backend: ClassificationBackend,
) -> BoundedWork:
    """Judge whether load can exceed controlled work and resource limits.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited capacity facts and reduce the
    answers through a fixed table. Compare input rates, queues, concurrency, batching, memory,
    deadlines, admission, backpressure, load shedding, cancellation, and overload recovery. The
    model never selects the final category.

    Evidence
    --------
    The frozen evidence bundle contains producers, buffers, workers, limits, resource profiles,
    and overload behavior. Every yes or no answer requires a valid evidence ID. Missing,
    conflicting, duplicate, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    Finite offline inputs may be naturally bounded when their maximum is verified.

    Examples
    --------
    A bounded worker pool with queue admission is `backpressured`. Creating one task per
    unbounded message with no limit is `unbounded`. A fixed batch whose size is proven is
    `bounded`.

    References
    ----------
    Cites "Site Reliability Engineering", handling overload
    Cites "Reactive Streams specification", backpressure
    Cites "Release It", bulkheads and stability patterns
    """
    return await backend.classify(
        subject,
        category=BoundedWork,
        instructions=(
            "Ask the selected judgment backend for four independently cited capacity"
            "facts and reduce the answers through a fixed table. Compare input rates,"
            "queues, concurrency, batching, memory, deadlines, admission, backpressure,"
            "load shedding, cancellation, and overload recovery. The model never selects"
            "the final category."
        ),
    )
