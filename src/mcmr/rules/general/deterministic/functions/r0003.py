from ..... import rule
from .....facts import FunctionFact, Visibility


@rule
def class_owned_module_helper(
    subject: FunctionFact,
    *,
    minimum_lines: int = 2,
    ignore_names: tuple[str, ...] = (),
) -> bool:
    """Detect a module helper used exclusively by one class method.

    Definition
    ----------
    Inspect undecorated module functions with one leading underscore and at least `minimum_lines`
    executable lines. Report only when the complete analyzed source set contains exactly one
    static load of the helper, that load is a direct call in a method body, and the method is
    defined directly on one class. This proves a narrow class-owned behavior candidate without
    rejecting private functional decomposition generally.

    Evidence
    --------
    Each finding cites the helper definition, owning class, method, and sole direct call. The rule
    proposes no automatic move because conversion may require `self`, `cls`, or a static method.

    Exceptions
    ----------
    Module-private helpers called by module functions are permitted. Additional references,
    multiple callers, callback capture, attribute access, cross-file uses, decorators, module
    dunder hooks, nested functions, and uncertain ownership fail closed without a finding. The
    one-line helper rule separately owns helpers below the default two-line floor. `ignore_names`
    retains a helper whose module-level position is deliberate, and `minimum_lines` is the floor
    below which the one-line helper rule owns the candidate instead.

    Examples
    --------
    Bad
    ~~~
    `_parse_response` has two implementation lines and its only project reference is the direct
    call `ApiClient.request -> _parse_response(...)`. It is a candidate for `ApiClient` ownership.

    Good
    ~~~~
    `_parse_response` called by a module function remains valid. Helpers shared by several methods,
    passed as callbacks, or referenced outside the defining file are not assigned to one class.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "A Philosophy of Software Design", chapters 4 and 5
    Cites "Agile Software Development", single responsibility principle
    """
    is_candidate = (
        subject.scope == "module"
        and subject.visibility is not Visibility.PUBLIC
        and not subject.decorators
        and subject.implementation_lines >= minimum_lines
        and subject.reference_count == 1
        and bool(subject.sole_reference_owner_class)
        and subject.name not in ignore_names
    )
    return is_candidate
