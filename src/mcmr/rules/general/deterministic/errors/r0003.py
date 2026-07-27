from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


@rule
def vanilla_error_type(
    subject: SyntaxFact,
    *,
    base_errors: tuple[str, ...] = (
        "Exception",
        "BaseException",
        "Error",
        "Throwable",
        "RuntimeException",
        "std::exception",
    ),
) -> Count:
    """Count failures raised as the language base error rather than as a named one.

    Definition
    ----------
    Read every raise one declaration states, take the type it names, and report the ones that
    name the base error the language ships. That is `Exception` and `BaseException` in Python,
    `Error` in JavaScript and TypeScript, `Throwable` and `RuntimeException` in Java, and
    `std::exception` in C++. A name that arrives qualified is judged on its last segment, so
    `builtins.Exception` reads the same as `Exception`.

    The cost lands on the caller rather than on the raiser. Handling this one failure means
    catching the base type, which also catches the typo, the missing key, and the bug three
    frames down, so the caller either swallows defects it never meant to see or gives up on
    recovery and lets everything through. A named type costs one line to declare and it turns
    the catch into a statement about what went wrong instead of a statement about anything at
    all going wrong.

    Evidence
    --------
    Each finding names the declaration, the raise, and the base type it constructs. The value is
    the number of raises a caller cannot single out.

    Exceptions
    ----------
    A bare re-raise carries the original type forward and constructs nothing, so it is left alone,
    and so is a raise of a value the code already holds such as a failure it caught a line above.
    The base names are a setting, because a project that declares its own root error may want that
    name reported too, and a language MCMR has not met yet spells its base differently. Only a
    callable is judged, because a type reaches every raise it owns through the callable holding it
    and would otherwise report the same one twice. `base_errors` is that list of names.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def load(path):
           if not path.exists():
               raise Exception(f"{path} is missing")

    Good
    ~~~~
    .. code-block:: python

       def load(path):
           if not path.exists():
               raise ProfileMissing(path)

    References
    ----------
    Generalizes Ruff TRY002 raise-vanilla-class
    https://docs.astral.sh/ruff/rules/raise-vanilla-class/
    Cites Pylint W0719 broad-exception-raised
    https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/broad-exception-raised.html
    Cites "The Python Tutorial", user defined exceptions
    https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions
    Cites "Clean Code", chapter 7, define exceptions in terms of a caller's needs
    """
    if subject.tree is None or subject.kind != "callable":
        return 0
    return sum(
        thrown.name.rsplit(".", 1)[-1] in base_errors
        for raised in subject.tree.of_kind("raise")
        for thrown in raised.of_kind("call", "name")[:1]
    )
