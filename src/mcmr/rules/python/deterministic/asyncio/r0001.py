from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def asyncio_run_boundary(
    subject: CallFact,
) -> Count:
    """Measure `asyncio.run` calls and enforce a single synchronous boundary.

    Definition
    ----------
    Resolve module-qualified and directly imported `asyncio.run` calls. Return the count for this
    call fact. A separate policy can enforce one synchronous boundary. The retained call sites
    expose async ownership for a separate nested-boundary rule.

    Evidence
    --------
    Evidence gives every call location, its enclosing function when present, and total call count.
    The value is the number of resolved `asyncio.run` calls.

    Exceptions
    ----------
    Independent executables can each own one event-loop boundary. Provider selection and policy
    configuration define that layout. When one synchronous process genuinely needs several
    top-level async calls in the same context, use one `asyncio.Runner`. Tests and experiments can
    be omitted by provider selection. This rule has no automatic lifecycle rewrite.

    Examples
    --------
    One CLI calling `asyncio.run(main())` once returns `1`. Three library functions each calling
    `asyncio.run` return `3`. A policy decides whether the measured boundary count fails.

    References
    ----------
    Cites "The Python Standard Library", asyncio runners
    https://docs.python.org/3/library/asyncio-runner.html
    """
    return subject.count_calls("asyncio.run")
