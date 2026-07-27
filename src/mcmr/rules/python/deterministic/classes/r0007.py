from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def utility_namespace_class_count(
    subject: ClassFact,
) -> Count:
    """Count classes that only namespace static or class functions.

    Definition
    ----------
    Inspect every class in the selected Python sources. Require at least one directly declared
    synchronous or asynchronous function. Report the class when every function has one or more
    decorators and every decorator is `staticmethod` or `classmethod`, while the class has no base
    other than `object`, no class keyword other than `metaclass=type`, and no instance-oriented
    field declaration. Uppercase constants and explicit `ClassVar` annotations remain class state
    and do not suppress the finding.

    Evidence
    --------
    Each finding identifies the class range, function count, and every qualifying function with
    its decorators. The result value is the number of utility namespace classes.

    Exceptions
    ----------
    Nontrivial inheritance and metaclasses exempt framework contracts, enums, Protocols, and ABCs.
    Lowercase annotated fields, `__slots__`, and attrs or dataclass field factories exempt
    data-bearing classes. Any instance method, property, abstract method, custom decorator, or
    undecorated function also exempts the whole class. The rule reports structure only and does not
    automatically move functions because public access paths and subclassing may be externally
    visible.

    Examples
    --------
    Bad
    ~~~
    `class TextTools` containing only `@staticmethod def normalize` and `@classmethod def parse`
    is reported because a module already provides the same namespace boundary.

    Good
    ~~~~
    `class Record` with an annotated `value` field is accepted. A `Protocol`, `Enum`, ABC,
    framework subclass, property-bearing class, or class with an ordinary instance method is also
    accepted even when it contains static helpers.

    References
    ----------
    Adapts Pylint R0903 too-few-public-methods
    Cites "The Python Tutorial", modules as namespaces
    https://docs.python.org/3/tutorial/modules.html
    Cites "The Python Language Reference", class creation and metaclasses
    https://docs.python.org/3/reference/datamodel.html#customizing-class-creation
    Cites "The Python Standard Library", functions, `staticmethod`
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Standard Library", functions, `classmethod`
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    """
    return sum(
        bool(item.methods)
        and all(
            method.decorators and set(method.decorators) <= {"staticmethod", "classmethod"}
            for method in item.methods
        )
        and set(item.direct_bases) <= {"object"}
        and set(item.class_keywords) <= {"metaclass=type"}
        and not item.has_instance_fields
        for item in subject.classes
    )
