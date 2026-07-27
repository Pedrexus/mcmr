from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def deprecated_event_loop_policy_usage(
    subject: CallFact,
    *,
    python_minor: int = 14,
) -> Count:
    """Count event-loop policy APIs deprecated in Python 3.14.

    Definition
    ----------
    For a configured minimum Python 3 minor version of 14 or newer, resolve references to
    `get_event_loop_policy`, `set_event_loop_policy`, `AbstractEventLoopPolicy`,
    `DefaultEventLoopPolicy`, `WindowsSelectorEventLoopPolicy`, and
    `WindowsProactorEventLoopPolicy`. The value and findings count every reference.

    Evidence
    --------
    Every finding gives the deprecated asyncio member and its exact source range. The value is the
    number of deprecated policy references.

    Exceptions
    ----------
    A compatibility layer supporting older Python may temporarily retain policy code behind a
    version boundary. Python 3.14 applications should configure loops through `loop_factory` on
    `asyncio.run` or `asyncio.Runner`. No automatic rewrite is safe because policy subclasses can
    own arbitrary process-wide behavior. `python_minor` is the Python 3 minor version the project
    targets, and the rule reports nothing below 14 because these names are not deprecated there.

    Examples
    --------
    `asyncio.set_event_loop_policy(CustomPolicy())` is reported for Python 3.14. Passing
    `loop_factory=uvloop.new_event_loop` to one runner is accepted. A Python 3.13 configuration
    produces no finding.

    References
    ----------
    Cites "The Python Standard Library", asyncio policy deprecations
    https://docs.python.org/3/library/asyncio-policy.html
    Cites "The Python Standard Library", asyncio runners and `loop_factory`
    https://docs.python.org/3/library/asyncio-runner.html
    """
    deprecated = frozenset(
        {
            "asyncio.get_event_loop_policy",
            "asyncio.set_event_loop_policy",
            "asyncio.AbstractEventLoopPolicy",
            "asyncio.DefaultEventLoopPolicy",
            "asyncio.WindowsSelectorEventLoopPolicy",
            "asyncio.WindowsProactorEventLoopPolicy",
        }
    )
    if python_minor < 14:
        return 0
    return subject.count_calls(*deprecated)
