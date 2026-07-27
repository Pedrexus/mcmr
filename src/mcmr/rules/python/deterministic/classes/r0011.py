from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def hazardous_multiple_inheritance_mro_count(
    subject: ClassFact,
) -> Count:
    """Count deterministic MRO hazards among project-owned direct bases.

    Definition
    ----------
    Build the project inheritance graph and inspect undecorated classes with at least two resolved
    project-owned direct bases. Report a class when one direct base already inherits another, or
    when several direct bases provide the same concrete method and at least one implementation
    does not delegate that same method through zero-argument `super()`. Abstract methods,
    overloads, ellipsis or `pass` stubs, and `NotImplementedError` placeholders do not create a
    collision. Disjoint or fully cooperative mixins remain accepted.

    Evidence
    --------
    Each finding records base order, concrete colliding method owners, redundant ancestor edges,
    and the complete subclass range. Measurements expose the number of project bases, collisions,
    and precedence edges separately. The value is the number of classes carrying a proven
    order-sensitive hierarchy.

    Exceptions
    ----------
    External bases are not guessed. Decorated classes and classes with metaclass or other keywords
    are excluded because frameworks can define their own linearization contract. A collision is
    accepted when every direct implementation explicitly participates in cooperative dispatch.
    Composition may still be preferable, but this rule reports only proven order sensitivity.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class JsonLoader:
           def load(self) -> bytes:
               return b"json"

       class CachedLoader:
           def load(self) -> bytes:
               return b"cache"

       class Service(JsonLoader, CachedLoader):
           pass

       class Specialized(Base, BaseContract):
           pass

    Good
    ~~~~
    .. code-block:: python

       class TimestampMixin:
           def timestamp(self) -> float:
               return time.time()

       class NamedMixin:
           def name(self) -> str:
               return type(self).__name__

       class Record(TimestampMixin, NamedMixin):
           pass

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Cites "Python HOWTOs", method resolution order
    https://docs.python.org/3/howto/mro.html
    Cites "The Python Standard Library", zero-argument super
    https://docs.python.org/3/library/functions.html#super
    Cites "Python's super() Considered Super"
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    """
    return sum(
        len(item.direct_bases) >= 2
        and not item.decorators
        and (item.has_redundant_direct_base or item.has_noncooperative_concrete_collision)
        for item in subject.classes
    )
