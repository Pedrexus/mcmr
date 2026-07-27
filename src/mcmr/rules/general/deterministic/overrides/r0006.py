from ..... import rule
from .....facts import OverrideFact
from .....models import Count

# What a decorator is called when it says a member is a promise rather than behavior, which is
# also what says a base has no initializer worth running.
_PROMISES = frozenset(
    {"abstractmethod", "abstractproperty", "abstractclassmethod", "abstractstaticmethod"}
)


@rule
def subclass_initializer_skips_its_base(subject: OverrideFact) -> Count:
    """Count subclasses that write their own initializer and never run the one above them.

    Definition
    ----------
    Report a direct base that declares an initializer where the subclass declares one too and
    reaches neither `super` nor that base from inside it. Half a constructor ran, so the object
    exists and every attribute the base was going to set is simply missing. The first read of one
    raises an attribute error somewhere unrelated, and the reader who lands there has no reason to
    suspect a constructor, which is why this costs an afternoon rather than a minute.

    Finding the skipped initializer means resolving the base across the repository and then
    reading what the subclass initializer actually calls. Both halves live in the graph, and
    neither is visible from the subclass alone.

    Evidence
    --------
    Each finding names the subclass, the base whose initializer never ran, and the receivers the
    subclass initializer did call. The value is one for each base left unrun.

    Exceptions
    ----------
    Only a direct base is judged, because an initializer that calls `super` hands the rest of the
    chain to Python and a class further up is not the subclass's to call. A base whose initializer
    is marked abstract has nothing to run. A subclass with no initializer of its own inherits the
    base one intact and is not judged at all.

    A base that runs its setup somewhere other than an initializer is a design MCMR cannot see,
    and a project built that way turns this rule off rather than adding empty calls. Pylint also
    skips an initializer marked as a typing overload and a base that is a protocol, and neither
    exemption is read here.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Connection:
           def __init__(self):
               self.socket = open_socket()


       class PooledConnection(Connection):
           def __init__(self):
               self.pool = []

    Good
    ~~~~
    .. code-block:: python

       class PooledConnection(Connection):
           def __init__(self):
               super().__init__()
               self.pool = []

    References
    ----------
    Generalizes Pylint W0231 super-init-not-called
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/super-init-not-called.html
    Cites "Python's super() Considered Super", PyCon 2015
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    Cites "The Python Language Reference", the method resolution order
    """
    declared = {item.name for item in subject.declared}
    reached = {*subject.initializer_calls} & {"super", subject.base.rsplit(".", 1)[-1]}
    return sum(
        subject.depth == 1
        and "__init__" in declared
        and not reached
        and not _PROMISES & {name.rsplit(".", 1)[-1] for name in item.decorators}
        for item in subject.inherited
        if item.name == "__init__"
    )
