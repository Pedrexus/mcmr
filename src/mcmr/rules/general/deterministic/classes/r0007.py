from ..... import rule
from .....facts import ClassFact, MemberKind, Visibility
from .....models import Count


@rule
def public_method_count(subject: ClassFact) -> Count:
    """Measure the widest public callable surface one type in this module declares.

    Definition
    ----------
    Count the callables one type declares in its own body whose resolved visibility is public and
    whose name a language does not reserve for its own protocol. Return the largest count any type
    in this module reaches, so the module is judged by its widest type rather than by an average
    that a file full of small helpers would hide. Inherited members do not count, because the
    surface a reader has to learn when opening this file is the one written here.

    Every language that declares members inside a type takes part. A provider maps its own spelling
    onto the shared visibility, so a Java `public` method, a Rust `pub fn` in an `impl` block, a
    TypeScript member that is neither `private` nor `#`-prefixed, and a Python name without a
    leading underscore are all counted the same way. A constructor, an operator, and a Python
    dunder are protocol names rather than surface a caller chooses to use, so they stay out.

    The count is the measurement and a project policy owns the ceiling. A repository facade and a
    value object sit at opposite ends of what is reasonable, and only a project can say which one
    it is looking at.

    Evidence
    --------
    Each finding records the class range and every counted member with its kind and visibility. The
    value is the number of public callables the widest type in this module declares.

    Exceptions
    ----------
    Data members are counted by the neighbouring field rule rather than here, so a wide record and
    a wide interface stay two different findings with two different repairs. A module that declares
    no type at all measures zero rather than being skipped, which keeps the value comparable across
    every file in a repository.

    Examples
    --------
    A class declaring `open`, `read`, `close`, `__init__`, `__repr__`, and `_reset` returns `3`,
    since the two dunders are protocol names and `_reset` is not public. The same three methods
    split across two classes in one module return `2` and `1`, and the module measures `2`.

    References
    ----------
    Generalizes Pylint R0904 too-many-public-methods
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-public-methods.html
    Generalizes Ruff PLR0904 too-many-public-methods
    https://docs.astral.sh/ruff/rules/too-many-public-methods/
    Generalizes SonarSource S1448
    https://rules.sonarsource.com/python/RSPEC-1448/
    Cites "Clean Code", chapter 10, classes should be small
    """
    return max(
        (
            sum(
                member.kind is not MemberKind.FIELD
                and member.visibility is Visibility.PUBLIC
                and not member.is_protocol_name
                for member in item.methods
            )
            for item in subject.classes
        ),
        default=0,
    )
