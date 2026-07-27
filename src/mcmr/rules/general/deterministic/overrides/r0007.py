from ..... import rule
from .....facts import OverrideFact
from .....models import Count


@rule
def initializer_called_on_a_stranger(subject: OverrideFact) -> Count:
    """Count initializers a subclass runs on a class it does not actually inherit from.

    Definition
    ----------
    Read what the subclass initializer calls, and report a call to the initializer of a class the
    subclass never names as a base. Running someone else's constructor on your own instance is
    borrowing setup by hand. It works right up to the day that class changes what it sets, and
    then a type the reader never connected to this one starts failing, because the only thing
    binding them together was a line nobody documented.

    It is usually a copy of the right line with the wrong name in it, which is exactly the kind
    of mistake the inheritance chain can prove and a reader cannot.

    Evidence
    --------
    Each finding names the subclass, the stranger whose initializer it ran, and the bases the
    subclass actually declares. The value is the number of stranger initializers called.

    Exceptions
    ----------
    A call reaching `super` is never a stranger, since Python picks the class it lands on. A call
    naming any declared base is what this rule exists to allow. The judgment is made once per
    subclass, on the link to the base a reader meets first, so a class with two bases counts one
    stray call once rather than once per base.

    A class assigned to a local name before its initializer is called is invisible, because the
    graph resolves the receiver as written. A deliberate mixin composed by hand rather than by
    inheritance is a legitimate design that this rule reports, and a project built that way turns
    it off.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Report(Document):
           def __init__(self):
               Spreadsheet.__init__(self)

    Good
    ~~~~
    .. code-block:: python

       class Report(Document, Spreadsheet):
           def __init__(self):
               super().__init__()

    References
    ----------
    Generalizes Pylint W0233 non-parent-init-called
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/non-parent-init-called.html
    Cites "Python's super() Considered Super", PyCon 2015
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    Cites "Design Patterns", prefer composition over inheritance
    """
    first = subject.base_names[0] if subject.base_names else ""
    return sum(
        subject.depth == 1
        and first == subject.base.rsplit(".", 1)[-1]
        and name != "super"
        and name not in subject.base_names
        for name in subject.initializer_calls
    )
