from ..... import rule
from .....facts import FunctionFact
from .....models import Choice, Finding, Measurement, Reported


@rule
def compact_house_docstring(subject: FunctionFact, *, maximum_summary: int = 99) -> Reported[bool]:
    """Enforce compact self-contained house docstrings where documentation exists.

    Definition
    ----------
    For every docstring a method or a function states, require a nonempty punctuated one-line
    summary within `maximum_summary`. Reject summaries that only send the reader elsewhere, Google
    or NumPy Args and Returns headings, and reStructuredText field lists. Accept compact
    `name: description` lines and require their description to be nonempty. Missing callable
    docstrings are left to dedicated coverage tools, and a module docstring belongs to the module
    family rather than to this one.

    Evidence
    --------
    Each finding points at the callable that owns the docstring and names which of the two shapes
    broke, the summary line or the body beneath it, beside how long the summary runs against what
    this project accepts. More than one violation in the same docstring stays a separate finding.
    The repair is a choice, since only the author knows what the sentence was trying to say.

    Exceptions
    ----------
    A docstring may contain technical reStructuredText sections, examples, directives, URLs, and
    references after its self-contained summary. Attribute documentation and ordinary multiline
    string values are not docstrings. Externally required doc formats can disable the rule at that
    adapter boundary.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def encode(text: str) -> list[int]:
           '''See the tokenizer documentation.

           Args:
               text: Input text.
           Returns:
               Token IDs.
           '''

    Good
    ~~~~
    .. code-block:: python

       def encode(text: str) -> list[int]:
           '''Encode text to token IDs.

           text: Input string to tokenize.
           '''

    References
    ----------
    Cites "PEP 257, Docstring Conventions"
    https://peps.python.org/pep-0257/
    Cites "The Python Developer's Guide"
    https://devguide.python.org/documentation/markup/
    Cites "Ruff documentation", pydocstyle rules
    https://docs.astral.sh/ruff/rules/#pydocstyle-d
    """
    if not subject.docstring:
        return Reported(value=False)
    lines = subject.docstring.strip().splitlines()
    summary = lines[0].strip() if lines else ""
    invalid_summary = (
        not summary
        or len(summary) > maximum_summary
        or summary[-1:] not in {".", "!", "?"}
        or summary.casefold().startswith(("see ", "refer to "))
    )
    forbidden_headings = {"args:", "arguments:", "returns:", "parameters", "returns"}
    invalid_body = any(
        line.strip().casefold() in forbidden_headings
        or line.lstrip().startswith((":param", ":return", ":rtype"))
        or ":" in line
        and not line.split(":", 1)[1].strip()
        for line in lines[1:]
    )
    findings = [
        Finding(
            message=message,
            span=subject.span,
            measurements=(
                Measurement(name="characters in the summary", value=len(summary)),
                Measurement(name="characters this project accepts", value=maximum_summary),
            ),
            repair=Choice(question=question),
        )
        for broken, message, question in (
            (
                invalid_summary,
                f"the docstring of `{subject.name}` opens with {len(summary)} characters that do "
                f"not read as one finished sentence",
                f"rewrite the first line of `{subject.name}` as one sentence under "
                f"{maximum_summary} characters",
            ),
            (
                invalid_body,
                f"the docstring of `{subject.name}` carries a heading or a label where this "
                f"project writes plain lines",
                f"drop the headings from `{subject.name}` and write `name` and its description "
                f"on one line",
            ),
        )
        if broken
    ]
    return Reported(value=invalid_summary or invalid_body, findings=tuple(findings))
