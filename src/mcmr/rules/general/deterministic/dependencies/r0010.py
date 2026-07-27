from fnmatch import fnmatch

from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def repeated_external_unary_transformation(
    subject: CallFact,
    *,
    minimum_repetitions: int = 3,
    minimum_files: int = 2,
    ignored_callables: tuple[str, ...] = (),
    first_party_modules: tuple[str, ...] = (),
    include: tuple[str, ...] = ("src/**",),
    exclude: tuple[str, ...] = ("vendored/**", "**/vendored/**"),
) -> Count:
    """Find repeated unary transformations performed directly by external packages.

    Definition
    ----------
    Resolve absolute module and symbol imports to fully qualified third-party callables. Count
    calls with exactly one explicit positional argument and no keywords, then group identical
    callables across project files. Report a project-owned boundary candidate only after a group
    reaches both `minimum_repetitions` and `minimum_files`. Relative imports, standard-library
    imports, inferred or configured first-party modules, constructors, shadowed bindings,
    ambiguous aliases, decorator factories, starred arguments, and configured
    `ignored_callables` are excluded.

    Evidence
    --------
    Each finding records the external callable, occurrence and file counts, every matching source
    location, and a stable project-boundary candidate identifier. The result value counts all
    eligible external unary calls, including one-offs that do not produce findings.

    Exceptions
    ----------
    Repetition alone does not prove a useful domain abstraction. Ignore a callable when direct use
    is itself the project convention, or raise the thresholds when a wrapper would only rename a
    stable dependency API. Configure additional first-party roots for nonstandard source layouts.
    `include` and `exclude` are the path globs that decide which sources are read, defaulting to
    everything under `src` and nothing vendored, and `first_party_modules` names the roots a
    nonstandard layout owns so its own code is not read as third party.

    Examples
    --------
    Bad
    ~~~
    Calling `inflection.underscore(value)` in three modules couples project naming policy to the
    external package at three sites.

    Good
    ~~~~
    Define one project function such as `python_name(value)` that calls
    `inflection.underscore(value)`, then depend on that named boundary. A single direct call or a
    call using keyword arguments does not trigger a finding.

    References
    ----------
    Cites "Refactoring", Extract Function
    https://refactoring.com/catalog/extractFunction.html
    Cites "Domain-Driven Design", Anti-Corruption Layer
    Cites "The Python Language Reference", the import system
    https://docs.python.org/3/reference/import.html
    """
    selected = [
        call
        for call in subject.calls
        if call.is_external
        and not call.is_standard_library
        and not call.is_first_party
        and not call.is_constructor
        and not call.is_shadowed
        and not call.has_ambiguous_alias
        and not call.is_decorator_factory
        and not call.has_starred_arguments
        and len(call.arguments) == 1
        and not call.keyword_names
        and call.qualified_name not in ignored_callables
        and not any(
            call.qualified_name == module or call.qualified_name.startswith(f"{module}.")
            for module in first_party_modules
        )
        and any(fnmatch(call.path, pattern) for pattern in include)
        and not any(fnmatch(call.path, pattern) for pattern in exclude)
    ]
    groups = {call.qualified_name for call in selected}
    return sum(
        sum(call.qualified_name == name for call in selected) >= minimum_repetitions
        and len({call.path for call in selected if call.qualified_name == name}) >= minimum_files
        for name in groups
    )
