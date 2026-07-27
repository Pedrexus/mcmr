from ..... import rule
from .....facts import ClassFact, MemberKind
from .....models import Count


@rule
def staticmethod_calling_classmethod_count(
    subject: ClassFact,
) -> Count:
    """Count static methods that hard-code their owner to call a sibling class method.

    Definition
    ----------
    Inspect methods declared directly in each class. Report a method only when its sole decorator
    is `staticmethod`, the same class directly declares at least one `classmethod`, and the static
    body calls that sibling through the literal owning class name. Calls inside nested functions
    and methods whose local bindings shadow the class name are excluded. The result is the number
    of affected static methods.

    Evidence
    --------
    Each finding identifies the static method and every sibling class method it calls. The literal
    owner reference is the proof that the method already depends on class-level behavior. The value
    is the number of static methods calling a sibling class method through the owner name.

    Exceptions
    ----------
    Calls to another class, an instance method, a static sibling, or an inherited method are not
    inferred. Custom-decorated static methods are excluded because changing descriptor order may
    alter framework behavior. A deliberate non-polymorphic call to one concrete class may remain
    static when the project documents that choice and disables this preference.

    Examples
    --------
    Bad
    ~~~
    `Parser.decide` is a static method whose body calls `Parser.from_text(...)`, where `from_text`
    is a class method. Subclasses cannot redirect that hard-coded call.

    Good
    ~~~~
    Make `decide` a class method, accept `cls`, and call `cls.from_text(...)`. A static method that
    only calls another static method remains unchanged.

    References
    ----------
    Cites "The Python Standard Library", `classmethod`
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "The Python Standard Library", `staticmethod`
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Language Reference", descriptor invocation
    https://docs.python.org/3/reference/datamodel.html#invoking-descriptors
    """
    return sum(
        method.kind is MemberKind.STATIC_METHOD
        and method.decorators == ["staticmethod"]
        and any(
            f"{item.name}.{sibling.name}" in method.owner_qualified_calls
            for sibling in item.methods
            if sibling.kind is MemberKind.CLASS_METHOD
        )
        for item in subject.classes
        for method in item.methods
    )
