from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def default_executor_to_thread_candidate(
    subject: CallFact,
    *,
    python_minor: int = 14,
) -> Count:
    """Count default-executor calls that can usually use `asyncio.to_thread`.

    Definition
    ----------
    For Python 3.9 or newer, find `run_in_executor(None, callable, *args)` calls on a loop obtained
    from `asyncio.get_running_loop` or `get_event_loop`. The first `None` selects the default
    thread executor. The value is the number of candidates.

    Evidence
    --------
    Every finding identifies the call and its nearest enclosing function. The value is the number
    of default-executor calls that could become `asyncio.to_thread`.

    Exceptions
    ----------
    Keep `run_in_executor` when selecting a custom executor, retaining a specific Future contract,
    or deliberately avoiding `contextvars` propagation. `asyncio.to_thread` is for blocking work
    that should not block the event loop. It does not turn coroutine execution into threading and
    does not generally make CPU-bound Python code parallel on a GIL-enabled build. `python_minor`
    is the Python 3 minor version the project targets, and the rule reports nothing below 9 because
    `asyncio.to_thread` does not exist there.

    Examples
    --------
    `await loop.run_in_executor(None, read_file, path)` is reported and can usually become
    `await asyncio.to_thread(read_file, path)`. Passing an explicit process, interpreter, or thread
    executor is accepted.

    References
    ----------
    Cites "The Python Standard Library", `asyncio.to_thread`
    https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
    Cites "The Python Standard Library", asyncio multithreading guidance
    https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading
    """
    if python_minor < 9:
        return 0
    return sum(
        call.qualified_name.endswith(".run_in_executor")
        and call.receiver is not None
        and call.receiver.qualified_name in {"asyncio.get_running_loop", "asyncio.get_event_loop"}
        and len(call.arguments) >= 2
        and call.arguments[0].text == "None"
        for call in subject.calls
    )
