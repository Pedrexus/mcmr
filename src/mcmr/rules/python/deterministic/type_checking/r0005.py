from collections import Counter

from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def repeated_cast_patterns(subject: CallFact, *, minimum_repetitions: int = 3) -> Count:
    """Count casts and flag structurally repeated cast patterns.

    Definition
    ----------
    Count every call resolved to `typing.cast` or `typing_extensions.cast` across the cached
    project sources. Group calls by target type and normalized producer pattern. Subscript keys
    and literal values are ignored, while container names, attributes, and callees remain part of
    the pattern. A group with at
    least `minimum_repetitions` occurrences is an anti-pattern finding because repetition usually
    means the same missing type contract is being overridden at several call sites. The count
    remains observable even when no repeated pattern is large enough to flag.

    Evidence
    --------
    Each finding reports the repeated target and producer pattern, occurrence count, affected file
    count, representative location, and up to 32 exact source locations. The suggested repair
    points toward one boundary validation, a typed model or TypedDict, a type guard, a Protocol, a
    generic, or an overload. Isolated casts remain in the count without becoming a finding. The
    value is the number of casts rather than the number of repeated patterns among them.

    Exceptions
    ----------
    A cast can be appropriate at an untyped or incorrectly typed third-party boundary because
    `cast` is a static assertion and performs no runtime validation. Even boundary casts become a
    finding when the same assertion is repeated. Validate or wrap that boundary once instead.

    Examples
    --------
    Bad
    ~~~
    Three calls such as `cast(str, row["id"])`, `cast(str, row["name"])`, and
    `cast(str, row["owner"])` form the pattern `str` from `subscript row`. Parse `row` once as
    a typed record instead of asserting every field independently.

    Good
    ~~~~
    One cast around the result of an untyped extension API is counted but not flagged. Replacing
    repeated casts with `Record.model_validate(raw)` creates one runtime boundary and typed uses
    after it.

    References
    ----------
    Cites "Python typing specification", Type checker directives, `cast()`
    https://typing.python.org/en/latest/spec/directives.html#cast
    Cites "Mypy documentation", `redundant-cast`
    https://mypy.readthedocs.io/en/stable/error_code_list2.html#check-that-cast-is-not-redundant-redundant-cast
    Cites "Pyright documentation", configuration, `reportUnnecessaryCast`
    https://github.com/microsoft/pyright/blob/main/docs/configuration.md
    """
    patterns = Counter(
        (call.arguments[0].text, call.arguments[1].qualified_name)
        for call in subject.calls
        if call.qualified_name in {"typing.cast", "typing_extensions.cast"}
        and len(call.arguments) == 2
    )
    return sum(count >= minimum_repetitions for count in patterns.values())
