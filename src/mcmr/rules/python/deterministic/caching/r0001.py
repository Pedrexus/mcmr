from ..... import rule
from .....facts import FunctionFact


@rule
def instance_independent_cached_property(
    subject: FunctionFact,
) -> bool:
    """Avoid storing an instance cache for a computation independent of that instance.

    Definition
    ----------
    Inspect direct synchronous and asynchronous class methods decorated with `cached_property`.
    Report a property whose executable body is one statement that never reads the receiver the
    method was handed. Nothing about the value depends on the instance, yet it is computed and
    stored again in every owner. Prefer a direct module function for stateless work. For expensive
    shared initialization, expose a module function backed by `functools.cache` or use an explicit
    singleton contract when identity is part of the design.

    Evidence
    --------
    Each finding identifies the owner, property, source range, and the proven absence of any read
    of the receiver in the executable body. The Boolean result identifies one property caching an
    instance independent value.

    Exceptions
    ----------
    A property whose body reads `self` or `cls` anywhere is accepted, as is one whose body does
    more than a single statement, since the storage may then be paying for real work the receiver
    took part in. A static method holds no receiver to read and never matches. Properties injected
    by frameworks, generated code, and vendored code can be excluded by path.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       @cached_property
       def prose_collector(self) -> ProseCollector:
           return ProseCollector()

    Good
    ~~~~
    .. code-block:: python

       @cached_property
       def prose_collector(self) -> ProseCollector:
           return ProseCollector(self.width)

       @cache
       def model() -> Model:
           return Model.load()

    References
    ----------
    Cites "The Python Standard Library", functools.cached_property
    https://docs.python.org/3/library/functools.html#functools.cached_property
    Cites "The Python Standard Library", functools.cache
    https://docs.python.org/3/library/functools.html#functools.cache
    """
    return (
        subject.scope == "method"
        and subject.cache_decorator == "cached_property"
        and not subject.reads_receiver
        and subject.direct_statement_count == 1
    )
