import sys
from collections.abc import Callable, Sequence
from math import ceil
from os import cpu_count
from typing import TYPE_CHECKING

import anyio
from anyio.to_thread import run_sync
from pydantic import PositiveInt

from .bases import FrozenFlexModel

if TYPE_CHECKING:
    from anyio.abc import ObjectReceiveStream

type Work[Value] = Callable[[], Value]


def available_workers(ceiling: int = 6) -> int:
    """Return how many rule batches may run at once on this interpreter.

    A build that still holds the GIL gains nothing from threads for pure rule work, so it stays
    deterministic at one worker. A free-threaded build runs real CPU parallelism, and the ceiling
    keeps contention below the point where added threads stop paying for themselves.
    """
    if sys._is_gil_enabled():
        return 1
    return max(1, min(ceiling, (cpu_count() or 1) - 1))


class WorkerPool(FrozenFlexModel):
    """Run ordered synchronous batches through one bounded worker stream.

    Work is submitted per batch rather than per rule. One fact carries every rule that reads it,
    so batching by fact keeps a submission from costing more than the work it carries and keeps
    the fact resident while its rules run. Results come back in submission order, so a report
    never depends on which worker finished first.
    """

    workers: int = 1
    chunks_per_worker: PositiveInt = 4

    def chunked[Item](self, work: Sequence[Item]) -> list[Sequence[Item]]:
        """Split work into few enough pieces that a handoff costs less than the piece.

        One fact is far too small to pay for a thread handoff, so facts travel in groups. The
        group count stays a small multiple of the worker count, which keeps every worker fed
        without letting a slow group decide when the whole run finishes.
        """
        if not work:
            return []
        groups = min(len(work), self.workers * self.chunks_per_worker)
        size = ceil(len(work) / groups)
        return [work[start : start + size] for start in range(0, len(work), size)]

    async def map[Value](self, calls: Sequence[Work[Value]]) -> list[Value]:
        """Run every call under the worker limit and restore the supplied order."""
        if not calls:
            return []
        if self.workers == 1:
            return [await run_sync(call) for call in calls]
        limiter = anyio.CapacityLimiter(self.workers)
        results: dict[int, Value] = {}
        send, receive = anyio.create_memory_object_stream[tuple[int, Work[Value]]](
            max_buffer_size=self.workers
        )
        streams = [receive, *(receive.clone() for _ in range(min(self.workers, len(calls)) - 1))]

        async def produce() -> None:
            async with send:
                for item in enumerate(calls):
                    await send.send(item)

        async def consume(stream: ObjectReceiveStream[tuple[int, Work[Value]]]) -> None:
            async with stream:
                async for index, call in stream:
                    results[index] = await run_sync(call, limiter=limiter)

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(produce)
                for stream in streams:
                    group.start_soon(consume, stream)
        except BaseExceptionGroup as failures:
            raise self.leaf(failures) from None
        return [results[index] for index in range(len(calls))]

    @staticmethod
    def leaf(failures: BaseExceptionGroup[BaseException]) -> BaseException:
        """Return the first failure inside a task group, with its own type and message.

        A rule that raises should reach the caller as that rule's error. The group is how the
        workers were run, not what went wrong, and the first failure is the one that cancelled
        the rest.
        """
        failure: BaseException = failures
        while isinstance(failure, BaseExceptionGroup):
            failure = failure.exceptions[0]
        return failure
