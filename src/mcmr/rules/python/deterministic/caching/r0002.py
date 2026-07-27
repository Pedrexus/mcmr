from ..... import rule
from .....facts import FunctionFact


@rule
def cached_instance_method(
    subject: FunctionFact,
) -> bool:
    """Avoid retaining object instances in function-wide method caches.

    Definition
    ----------
    Inspect direct class methods decorated with `functools.cache` or `functools.lru_cache`,
    including called decorator forms and qualified names. Report ordinary instance methods, which
    are the ones binding neither `classmethod` nor `staticmethod`, because Python includes `self`
    in the cache key and retains cached arguments until eviction or an explicit clear. Use
    `cached_property` for a zero-argument value owned by one instance. Move a computation
    independent of instance identity to a module-level cached function.

    Evidence
    --------
    Each finding identifies the class, method, cache decorator, and complete source range. The
    Boolean result identifies one cached instance method.

    Exceptions
    ----------
    Static methods and class methods are excluded because they do not retain ordinary instances.
    Generated and vendored code can be excluded by path. A deliberately bounded instance cache
    may disable this preference when its ownership and clearing behavior are explicit.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       @lru_cache(maxsize=128)
       def parse(self, text: str) -> Node:
           return self.parser.parse(text)

    Good
    ~~~~
    .. code-block:: python

       @cached_property
       def schema(self) -> Schema:
           return build_schema(self.fields)

       @cache
       def tokenizer(model: str) -> Tokenizer:
           return Tokenizer.load(model)

    References
    ----------
    Cites "The Python Standard Library", functools.lru_cache
    https://docs.python.org/3/library/functools.html#functools.lru_cache
    Cites "Python FAQ", caching methods
    https://docs.python.org/3/faq/programming.html#how-do-i-cache-method-calls
    """
    bindings = {decorator.split("(")[0].rsplit(".", 1)[-1] for decorator in subject.decorators}
    return (
        subject.scope == "method"
        and subject.cache_decorator in {"cache", "lru_cache"}
        and not subject.is_property
        and bindings.isdisjoint({"classmethod", "staticmethod"})
    )
