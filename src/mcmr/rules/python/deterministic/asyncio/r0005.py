from ..... import rule
from .....facts import CallFact
from .....models import Count, Replace, SourceRewrite


@rule
def deprecated_asyncio_coroutine_function_check(
    subject: CallFact,
    *,
    python_minor: int = 14,
) -> Count:
    """Count the coroutine function alias deprecated in Python 3.14.

    Definition
    ----------
    For a configured minimum Python 3 minor version of 14 or newer, resolve qualified,
    directly imported, and aliased references to `asyncio.iscoroutinefunction`. The result
    value and findings count every reference. Use `inspect.iscoroutinefunction` instead.

    Evidence
    --------
    Every finding identifies the exact deprecated reference and source range. The value is the
    number of deprecated alias references.

    Exceptions
    ----------
    A compatibility package that deliberately exposes the old spelling can exclude its
    compatibility module. Ordinary callers need no behavior change because the asyncio name is an
    alias of the inspect implementation. No automatic fix is offered until import edits can
    preserve aliases and remove newly unused imports safely. `python_minor` is the Python 3 minor
    version the project targets, and the rule reports nothing below 14 because the alias is not
    deprecated there.

    Examples
    --------
    `asyncio.iscoroutinefunction(callback)` is reported. So is
    `from asyncio import iscoroutinefunction as is_async`. Importing `inspect` and calling
    `inspect.iscoroutinefunction(callback)` is accepted. A Python 3.13 configuration produces
    no finding.

    References
    ----------
    Cites "What's New In Python"
    https://docs.python.org/3.14/deprecations/
    Cites "The Python Standard Library", inspect coroutine function predicate
    https://docs.python.org/3.14/library/inspect.html#inspect.iscoroutinefunction
    """
    if python_minor < 14:
        return 0
    return subject.count_calls("asyncio.iscoroutinefunction")


@deprecated_asyncio_coroutine_function_check.fix(is_default=True)
def replace_with_inspect(
    subject: CallFact,
    *,
    python_minor: int = 14,
) -> list[SourceRewrite]:
    """Point each deprecated check at the `inspect` function that replaced it."""
    return [
        Replace(target=call.callee, source="inspect.iscoroutinefunction")
        for call in subject.calls
        if call.qualified_name == "asyncio.iscoroutinefunction" and call.callee is not None
    ]
