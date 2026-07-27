from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def direct_method_descriptor_call_count(subject: CallFact) -> Count:
    """Count `staticmethod` and `classmethod` calls used without decorator syntax.

    Definition
    ----------
    Parse one Python source file and count direct calls to the built-in `staticmethod` or
    `classmethod` descriptor constructors. This includes their explicit `builtins` forms. Method
    binding policy should be visible next to the method declaration through `@staticmethod` or
    `@classmethod`, not reconstructed through assignment or a class-body alias.

    Evidence
    --------
    Each finding identifies the complete call range and the descriptor constructor that was
    invoked. A bare decorator is an AST decorator name rather than a call, so normal decorator
    syntax cannot trigger this rule. The value is the number of direct descriptor constructor
    calls.

    Exceptions
    ----------
    Python permits direct descriptor construction, so this is an explicit readability policy
    rather than a language error. Calls through dynamic aliases are not guessed. Projects that
    intentionally build descriptors or metaclasses dynamically can disable this rule for that
    narrow source boundary.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Parser:
           parse = staticmethod(parse)

       wrapped = classmethod(build)

    Good
    ~~~~
    .. code-block:: python

       class Parser:
           @staticmethod
           def parse(text: str) -> "Parser":
               return Parser(text)

           @classmethod
           def build(cls, text: str) -> "Parser":
               return cls(text)

    References
    ----------
    Cites "The Python Standard Library", staticmethod
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Standard Library", classmethod
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "Python HOWTOs", descriptor guide
    https://docs.python.org/3/howto/descriptor.html#static-methods-and-class-methods
    """
    return sum(
        call.qualified_name in {"builtins.staticmethod", "builtins.classmethod"}
        and not call.is_decorator_factory
        for call in subject.calls
    )
