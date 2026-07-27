from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def unbounded_blocking_call(
    subject: CallFact,
    *,
    bounded_callables: tuple[str, ...] = (),
    bound_names: tuple[str, ...] = ("timeout", "deadline", "duration"),
) -> Count:
    """Count calls that can wait forever because no bound was passed.

    Definition
    ----------
    Report a resolved call to a configured callable that names none of `bound_names` among its
    arguments. A network read, a subprocess wait, a lock acquisition, and a queue get all block
    until something else happens, and without a bound that something may never happen. The failure
    is a process that hangs rather than one that reports an error, which is why it survives review
    and testing and only appears in production.

    Evidence
    --------
    Each finding records the call range, the qualified name, and the argument names that were
    passed. The value is the number of unbounded calls.

    Exceptions
    ----------
    A deliberate wait, such as a supervisor joining its workers at shutdown or a server accepting
    connections, is legitimate and belongs outside the configured list. With no configured
    callables the rule reports nothing. A project whose bound travels in a context or a
    cancellation scope rather than an argument should name that pattern instead of this rule.
    `bounded_callables` names the calls a project considers blocking, which is why the rule reports
    nothing until somebody states them.

    Examples
    --------
    With `requests.get` configured, `requests.get(url)` returns `1` and
    `requests.get(url, timeout=5)` returns `0`.

    References
    ----------
    Cites Pylint W3101 missing-timeout
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/missing-timeout.html
    Cites "Release It", timeouts and the integration point failure mode
    Cites "The Python Standard Library", `subprocess` documentation on the timeout argument
    https://docs.python.org/3/library/subprocess.html#subprocess.Popen.wait
    """
    bounds = set(bound_names)
    return sum(
        call.qualified_name in bounded_callables and not bounds.intersection(call.keyword_names)
        for call in subject.calls
    )
