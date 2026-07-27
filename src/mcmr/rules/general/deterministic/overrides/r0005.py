from ..... import rule
from .....facts import MemberDeclaration, OverrideFact
from .....models import Count

# What a decorator is called when it says a member is a promise rather than behavior.
_PROMISES = frozenset(
    {"abstractmethod", "abstractproperty", "abstractclassmethod", "abstractstaticmethod"}
)


def promised(declaration: MemberDeclaration) -> bool:
    """Whether the class states this member as a promise somebody else has to keep."""
    return any(name.rsplit(".", 1)[-1] in _PROMISES for name in declaration.decorators)


@rule
def abstract_member_left_unimplemented(
    subject: OverrideFact,
    *,
    abstract_bases: frozenset[str] = frozenset({"ABC", "ABCMeta", "Protocol"}),
) -> Count:
    """Count promises a base made that the concrete subclass below it never kept.

    Definition
    ----------
    Read every member a base declares that the subclass never declares again, and report one the
    base marked as abstract when the subclass is meant to be instantiated. An abstract member is a
    contract written down, and a concrete class that leaves one open has published a type that
    raises the moment anybody uses the part nobody finished. The failure lands on whoever
    instantiates the class rather than on whoever wrote it, which is the wrong person and usually
    the wrong week.

    A class is read as abstract itself, and left alone, when it names a base such as `ABC` or
    `Protocol` anywhere above it or when it declares an abstract member of its own. Those are the
    two ways a class says it is a step on the way rather than a destination.

    Evidence
    --------
    Each finding names the subclass, the base that declared the promise, and the member left open.
    The value is the number of unkept promises.

    Exceptions
    ----------
    A class naming one of `abstract_bases` anywhere in its inheritance chain is left alone, and a
    project whose own base spells that differently states its own set. A subclass that redeclares
    the name as data has answered the promise, since something is there to find.

    Pylint also treats a body that only raises `NotImplementedError` as abstract, which is a
    convention rather than a declaration and leaves no decorator for a graph to read, so MCMR
    reports a subset of what Pylint reports rather than guessing at bodies. A metaclass passed as
    a keyword makes a class abstract too and leaves no inheritance edge behind, so that spelling
    is not seen either.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Encoder:
           @abstractmethod
           def encode(self, value): ...


       class JsonEncoder(Encoder):
           def describe(self):
               return "json"

    Good
    ~~~~
    .. code-block:: python

       class JsonEncoder(Encoder):
           def encode(self, value):
               return json.dumps(value)

    References
    ----------
    Generalizes Pylint W0223 abstract-method
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/abstract-method.html
    Cites "PEP 3119, Introducing Abstract Base Classes"
    https://peps.python.org/pep-3119/
    Cites "Design Patterns", the template method pattern
    """
    if abstract_bases & {*subject.ancestor_names} or any(map(promised, subject.declared)):
        return 0
    return sum(map(promised, subject.unanswered))
