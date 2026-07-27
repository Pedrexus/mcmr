from ..... import rule
from .....facts import FunctionFact


@rule
def task_group_candidate(
    subject: FunctionFact,
) -> bool:
    """Detect an async function manually pairing created tasks with `gather`.

    Definition
    ----------
    Within each async function, resolve `asyncio.create_task` or `ensure_future` together with an
    awaited or returned `asyncio.gather` whose `return_exceptions` is not true. Exclude functions
    already constructing `asyncio.TaskGroup`. The Boolean result identifies a candidate function.

    Evidence
    --------
    Findings identify the function and report syntactic task-creation and gather counts. The rule
    does not claim semantic equivalence.

    Exceptions
    ----------
    `gather` deliberately allows siblings to continue after one ordinary exception, while
    `TaskGroup` cancels remaining siblings and raises an exception group. Keep `gather` when that
    behavior, result ordering, partial success, or explicit cancellation protocol is required.
    Calls using `return_exceptions=True` are excluded. Review exception and cancellation contracts
    before changing code, so no automatic fix is offered.

    Examples
    --------
    Creating two tasks, gathering them, and manually canceling unfinished tasks is reported as a
    structured-concurrency candidate. Directly gathering independent coroutines without first
    creating tasks is accepted. Code already using `async with TaskGroup()` is accepted.

    References
    ----------
    Cites "The Python Standard Library", coroutine and TaskGroup
    https://docs.python.org/3/library/asyncio-task.html#task-groups
    Cites "The Python Standard Library", `gather`
    https://docs.python.org/3/library/asyncio-task.html#asyncio.gather
    """
    return (
        subject.is_async
        and subject.created_task_count > 0
        and subject.gather_consumes_created_tasks
        and not subject.gather_returns_exceptions
        and not subject.has_task_group
    )
