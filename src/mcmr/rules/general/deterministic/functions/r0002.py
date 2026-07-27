from ..... import rule
from .....facts import FunctionFact, Visibility
from .....models import FixSafety, Inline, SourceRewrite


@rule
def single_use_trivial_helper(
    subject: FunctionFact,
    *,
    maximum_lines: int = 1,
    ignore_names: tuple[str, ...] = (),
) -> bool:
    """Detect a private one-line helper with only one local reference.

    Definition
    ----------
    Inspect undecorated private functions declared directly at module scope. After omitting an
    optional docstring, require exactly one non-`pass`, non-`raise` statement, no more than
    `maximum_lines` executable lines, and exactly one loaded reference outside the function body
    in the same module. The Boolean result reports whether this function is a candidate.

    Evidence
    --------
    Each finding identifies the helper definition and its only local reference. The rule does not
    edit code because inlining can change evaluation order, exception location, or debugging.

    Exceptions
    ----------
    Public functions, methods, nested functions, decorated hooks, callbacks, fixtures, overloads,
    protocol implementations, recursive helpers, unused functions, and helpers with multiple
    references are excluded structurally. `ignore_names` retains a deliberate named boundary.
    Vulture remains responsible for functions with no uses.

    Examples
    --------
    Bad
    ~~~
    `_normalize = lambda` is not required. An undecorated `_normalize` whose body is only
    `return value.strip()` and which is called once is reported for possible inlining.

    Good
    ~~~~
    The same helper called from three sites remains. A decorated one-line route handler, a public
    adapter, and a multiline expression with one top-level `return` are not candidates.

    References
    ----------
    Cites "A Philosophy of Software Design", chapter 4, shallow modules
    Cites "Clean Code", chapter 3, small functions
    Cites "Vulture documentation", unused code boundary
    https://github.com/jendrikseipp/vulture
    """
    is_candidate = (
        subject.scope == "module"
        and subject.visibility is not Visibility.PUBLIC
        and not subject.decorators
        and subject.direct_statement_count == 1
        and subject.implementation_lines <= maximum_lines
        and subject.reference_count == 1
        and not subject.is_recursive
        and not subject.is_pass_body
        and not subject.is_raise_body
        and subject.name not in ignore_names
    )
    return is_candidate


@single_use_trivial_helper.fix(is_default=True, safety=FixSafety.REVIEW)
def inline_trivial_helper(
    subject: FunctionFact,
    *,
    maximum_lines: int = 1,
    ignore_names: tuple[str, ...] = (),
) -> list[SourceRewrite]:
    """Replace the single reference with the helper body, then delete the declaration."""
    if subject.definition is None or subject.body_expression is None or not subject.references:
        return []
    return [
        Inline(
            declaration=subject.definition,
            body=subject.body_expression,
            references=subject.references,
        )
    ]
