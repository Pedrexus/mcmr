from ..... import rule
from .....facts import MemberDeclaration, OverrideFact
from .....models import Count

# What a language writes in front of a member to say a caller reads it rather than calls it.
_READ_RATHER_THAN_CALLED = frozenset({"property", "cached_property"})


def read_as_data(declaration: MemberDeclaration) -> bool:
    """Whether the class states this member as something a caller reads instead of calls."""
    return any(
        name.rsplit(".", 1)[-1] in _READ_RATHER_THAN_CALLED
        or name.endswith((".setter", ".getter", ".deleter"))
        for name in declaration.decorators
    )


@rule
def overriding_method_changes_its_call_protocol(subject: OverrideFact) -> Count:
    """Count overrides that change how a caller has to reach the member, not just what it does.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report an override that changed the protocol rather than the behavior. Two changes count.
    Turning a property into a method, or a method into a property, moves the parentheses to the
    call site, so `thing.size` starts returning a bound method that is always truthy and never
    the number anyone wanted. Turning an awaitable into a plain call, or the reverse, is worse
    still, because a coroutine nobody awaits is silently discarded and the work never happens.

    Neither failure raises anything where it is written. Both surface far away, as a wrong number
    or as work that quietly did not run, and that distance is what makes them expensive.

    Evidence
    --------
    Each finding names the subclass, the base, the member, and how each side declared it. The
    value is the number of overrides that changed the protocol.

    Exceptions
    ----------
    A name Python rewrites into the class that wrote it, spelled with two leading underscores and
    no trailing ones, is left alone, because no subclass can override it in the first place. A
    member one side writes as data is judged by the hiding rule rather than here.

    A property implemented through a descriptor of the project's own making is not recognized,
    since the graph reads the decorator a class wrote and not what that decorator returns. Pylint
    reports the property and the async halves as separate messages on one method, so a member that
    changed both counts once here and twice there.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Source:
           async def read(self):
               return await self.stream.read()


       class CachedSource(Source):
           def read(self):
               return self.buffer

    Good
    ~~~~
    .. code-block:: python

       class CachedSource(Source):
           async def read(self):
               return self.buffer

    References
    ----------
    Generalizes Pylint W0236 invalid-overridden-method
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/invalid-overridden-method.html
    Cites "PEP 492, Coroutines with async and await"
    https://peps.python.org/pep-0492/
    Cites "The Python Language Reference", the descriptor protocol
    """
    return sum(
        read_as_data(inherited) != read_as_data(override)
        or inherited.asynchronous != override.asynchronous
        for inherited, override in subject.overrides
        if inherited.parameters is not None
        and override.parameters is not None
        and not (inherited.name.startswith("__") and not inherited.name.endswith("__"))
    )
