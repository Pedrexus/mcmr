from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


@rule
def dynamic_super_receiver(subject: SyntaxFact) -> Count:
    """Count `super` calls whose first argument is computed from the receiver.

    Definition
    ----------
    Report a method that calls a member on `super(type(self), self)` or on `super(self.__class__,
    self)`. Both spellings look like a way to avoid repeating the class name and both recurse
    forever the moment somebody subclasses the type, because the first argument is resolved at run
    time to the object's actual class, so the lookup restarts one step below where it started and
    reaches the same method again. The value is the number of such calls.

    Writing `super()` states the enclosing class at compile time and cannot make that mistake,
    which is why it is the only spelling worth having in a body that has one.

    Evidence
    --------
    The finding names the method and counts the calls inside it. A `super` object merely assigned
    to a name is not counted, since the defect is the lookup rather than the construction. The
    value is the number of `super` calls whose first argument is computed from the receiver.

    Exceptions
    ----------
    A first argument stating a class outright is left alone, even when it names an ancestor rather
    than the enclosing class, because skipping a step through the resolution order on purpose is a
    legal thing to do and telling it from an unrelated class needs the ancestors of the class
    beside the source of its methods, which no single fact carries.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Engine(Base):
           def run(self):
               return super(type(self), self).run()

    Good
    ~~~~
    .. code-block:: python

       class Engine(Base):
           def run(self):
               return super().run()

    References
    ----------
    Generalizes Pylint E1003 bad-super-call
    https://pylint.readthedocs.io/en/latest/user_guide/messages/error/bad-super-call.html
    Cites "The Python Standard Library", `super` and the zero-argument form
    https://docs.python.org/3/library/functions.html#super
    Cites "Python's super() Considered Super"
    https://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    """
    if subject.tree is None or subject.kind != "callable" or "." not in subject.qualname:
        return 0
    return sum(
        call.children[1].name in {"type", "__class__"}
        for member in subject.tree.of_kind("member")
        for call in member.children
        if call.kind == "call" and call.name == "super" and len(call.children) > 1
    )
