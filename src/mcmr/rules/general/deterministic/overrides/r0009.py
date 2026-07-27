from ..... import rule
from .....facts import OverrideFact


@rule
def final_class_subclassed(subject: OverrideFact) -> bool:
    """Detect a class that inherits from a class its author sealed against inheritance.

    Definition
    ----------
    Report a direct base decorated final. Sealing a class is the strongest statement an author can
    make about it, which is that the class reasons about its own state and was never designed to
    have a stranger reach into the middle of it. Subclassing one anyway means every invariant it
    documented is now a guess, and the author who sealed it is free to change anything at all in
    the next release because nobody was supposed to be standing there.

    The marker lives on the base, usually in another file, so the defect only exists as a relation
    between two classes and a resolved inheritance chain is the only thing that holds it.

    Evidence
    --------
    Each finding names the subclass, the sealed base, and the decorator that sealed it. The value
    says whether this link crosses a seal.

    Exceptions
    ----------
    Only a direct base is judged, because a class further up was sealed against whoever inherited
    it first and that is where the report belongs. A project sealing a class through a decorator
    of its own making is not read, since the graph records the decorator a class wrote and not
    what that decorator returns.

    A type checker also reports this, and it is worth reporting twice, because the marker exists
    to be enforced and a project that runs no type checker still deserves the answer.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       @final
       class Money:
           def __init__(self, cents):
               self.cents = cents


       class Discount(Money):
           def apply(self, rate):
               self.cents = int(self.cents * rate)

    Good
    ~~~~
    .. code-block:: python

       class Discount:
           def __init__(self, amount):
               self.amount = amount

    References
    ----------
    Generalizes Pylint W0240 subclassed-final-class
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/subclassed-final-class.html
    Cites "PEP 591, Adding a Final Qualifier to Typing"
    https://peps.python.org/pep-0591/
    Cites "Effective Java", design and document for inheritance or else prohibit it
    """
    return subject.depth == 1 and any(
        name.rsplit(".", 1)[-1] == "final" for name in subject.base_decorators
    )
