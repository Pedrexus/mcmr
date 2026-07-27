import sys

import pytest

from mcmr.concurrency import WorkerPool, available_workers


@pytest.mark.anyio
async def test_pool_restores_submission_order_under_parallel_workers() -> None:
    """Results follow the order the batches were submitted, not the order they finished."""
    pool = WorkerPool(workers=4)
    calls = [lambda index=index: index * 2 for index in range(12)]

    assert await pool.map(calls) == [index * 2 for index in range(12)]


def test_chunks_stay_within_the_worker_budget_and_cover_every_item() -> None:
    """Work is split into few enough groups to amortize a handoff, losing no item."""
    pool = WorkerPool(workers=3, chunks_per_worker=2)
    chunks = pool.chunked(list(range(20)))

    assert len(chunks) <= 6
    assert [item for chunk in chunks for item in chunk] == list(range(20))
    assert pool.chunked([]) == []
    assert len(WorkerPool(workers=8).chunked([1, 2])) == 2


@pytest.mark.anyio
async def test_pool_runs_a_single_worker_and_an_empty_batch_list() -> None:
    """One worker still leaves the event loop, and no work needs no stream at all."""
    assert await WorkerPool().map([lambda: "only"]) == ["only"]
    assert await WorkerPool(workers=4).map([]) == []


def test_worker_count_follows_the_interpreter_gil_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """A build holding the GIL stays deterministic while a free-threaded build scales out."""
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: True)
    assert available_workers() == 1

    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False)
    assert available_workers() >= 1
    assert available_workers(ceiling=2) <= 2
