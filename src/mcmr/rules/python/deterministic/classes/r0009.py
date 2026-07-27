from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def artificial_single_subclass_base_count(
    subject: ClassFact,
) -> Count:
    """Count concrete project bases that exist only for one closed-world subclass.

    Definition
    ----------
    Build a project-owned inheritance and import graph over the selected sources. Report a
    top-level base only when it has exactly one direct subclass and no other descendants, neither
    class has decorators or class keywords, the base has no parent except `object`, and the base
    is never instantiated. The base must be absent from `__all__` and package re-exports. Its sole
    cross-module import and every cross-module reference must belong to the subclass declaration.

    Evidence
    --------
    Each finding names the qualified base and subclass, records the subclass and import counts, and
    locates the complete base definition. The proof is deliberately closed-world and covers only
    the configured source snapshot. The value is the number of bases that exist only for their one
    subclass.

    Exceptions
    ----------
    Abstract methods, stubs, Protocols, exceptions, Pydantic and Patos models, external or
    framework parents, registries, strategies, backends, providers, components, and plugin APIs
    are excluded. Decorated classes, metaclasses, multiple inheritance, exported bases, star
    imports, extra references, multiple children, and descendant chains also abstain. Public
    extension points should remain explicit even when the current repository has one subclass.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       # support.py
       class ServiceSupport:
           def normalize(self, value: str) -> str:
               return value.strip()

       # service.py
       from .support import ServiceSupport

       class Service(ServiceSupport):
           pass

    Good
    ~~~~
    .. code-block:: python

       class Service:
           def normalize(self, value: str) -> str:
               return value.strip()

       class StoragePlugin(Protocol):
           def store(self, value: bytes) -> None: ...

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Cites "The Python Language Reference", custom classes
    https://docs.python.org/3.14/reference/datamodel.html#custom-classes
    Cites "The Python Standard Library", abc
    https://docs.python.org/3.14/library/abc.html
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    Cites "The Python Language Reference", import system, import-related module attributes
    https://docs.python.org/3.14/reference/import.html#import-related-module-attributes
    Cites "Python Packaging User Guide", creating and discovering plugins
    https://packaging.python.org/guides/creating-and-discovering-plugins/
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    """
    return sum(
        item.scope == "module"
        and len(item.direct_subclasses) == 1
        and item.descendant_count == 1
        and not item.decorators
        and not item.class_keywords
        and set(item.direct_bases) <= {"object"}
        and not item.is_instantiated
        and not item.is_exported
        and item.only_cross_module_reference_is_subclass
        for item in subject.classes
    )
