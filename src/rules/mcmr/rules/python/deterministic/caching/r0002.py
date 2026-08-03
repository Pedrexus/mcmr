import polars as pl

from ..... import rule
from .....facts import FunctionFact
from .....query import FindingQuery, RuleQuery
from .....table import FunctionRelation, Table


@rule("PY-CACH0002")
def cached_instance_method(
    subject: Table[FunctionFact],
) -> RuleQuery[bool]:
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
    bindings = (
        subject.lazy(FunctionRelation.DECORATORS)
        .with_columns(
            pl.col("decorator")
            .str.split("(")
            .list.first()
            .str.split(".")
            .list.last()
            .is_in(["classmethod", "staticmethod"])
            .alias("has_class_or_static_binding")
        )
        .group_by("function_id")
        .agg(pl.col("has_class_or_static_binding").any())
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            bindings,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("has_class_or_static_binding").fill_null(False))
    )
    value = (
        (pl.col("scope") == "method")
        & pl.col("cache_decorator").is_in(["cache", "lru_cache"])
        & ~pl.col("is_property")
        & ~pl.col("has_class_or_static_binding")
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "cached instance method"),
    )
