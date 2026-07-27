from itertools import pairwise

from ..... import rule
from .....facts import FunctionFact
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def swappable_parameter_pair(subject: FunctionFact) -> CountReport:
    """Count adjacent parameter pairs a caller can silently swap.

    Definition
    ----------
    Compare each pair of adjacent declared parameters and report a pair whose declared types are
    identical and non-empty. Identical adjacent types make a transposed call compile, type-check,
    and run, so nothing but a test can catch it. The count excludes the receiver, which a caller
    never passes explicitly.

    The type compared is the one a caller sees, which in a language writing half of its types in
    the declarator means the pointer, the reference, and the qualifiers that reach the value, not
    the word the declaration happens to name. `int32_t *tokens` and `int32_t start` share no type
    and no caller could transpose them, and neither could one swap `const int32_t *` with
    `int32_t *`, since that conversion runs one way only.

    Evidence
    --------
    Each finding records the callable range, both parameter names, the type they share, and
    where in the parameter list the pair sits. The repair is a choice between separating the two
    types and closing the position off, because only the author knows which one the caller wants.
    The value is the number of swappable adjacent pairs.

    Exceptions
    ----------
    A keyword-only parameter cannot be transposed, because its name travels with its value, so it
    is excluded. A qualifier a caller cannot observe does not separate two types, so `const int`
    beside `int` and `int *const` beside `int *` are each one pair rather than none. Parameters
    whose names make the order self-evident at the call site, such as `width` and `height`, still
    count because the risk lives in the call, not the declaration. The usual repairs are a distinct
    type for each role or a keyword-only contract, which is why a language with mandatory named
    arguments reports none.

    Examples
    --------
    `def copy(source: Path, destination: Path)` returns `1`. `def copy(source: Source, into: Sink)`
    returns `0`, and so does `def resize(*, width: int, height: int)` in a language that can force
    the names. `void merge(int32_t *left, int32_t *right)` returns `1` where
    `void merge(int32_t *left, int32_t count)` returns `0`.

    References
    ----------
    Generalizes clang-tidy bugprone-easily-swappable-parameters
    https://clang.llvm.org/extra/clang-tidy/checks/bugprone/easily-swappable-parameters.html
    Cites "Effective Java", item on parameter lists
    Cites "Refactoring", introduce parameter object
    """
    declared = [
        parameter
        for parameter in subject.parameters
        if not parameter.is_receiver and not parameter.is_keyword_only
    ]
    swappable = [
        (position, left, right)
        for position, (left, right) in enumerate(pairwise(declared), start=1)
        if left.type_name and left.type_name == right.type_name
    ]
    return Reported(
        value=len(swappable),
        findings=tuple(
            Finding(
                message=(
                    f"`{subject.name}` takes `{left.name}` and `{right.name}` next to each other "
                    f"and both are `{left.type_name}`, so a caller can transpose them silently"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="position in the parameter list", value=position),
                    Measurement(
                        name="parameters a caller can pass by position", value=len(declared)
                    ),
                ),
                repair=Choice(
                    question=f"stop `{left.name}` and `{right.name}` from being interchangeable",
                    options=(
                        "give each one the type it actually names",
                        "make the second one keyword-only",
                    ),
                ),
            )
            for position, left, right in swappable
        ),
    )
