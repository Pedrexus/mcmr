import re

from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


def handler_bodies(text: str, handlers: tuple[str, ...]) -> list[list[str]]:
    """Return the body lines every handler clause of one guard states.

    text: the exact source the guard spans, as the frontend read it.
    handlers: the words a language opens a handler clause with.
    """
    opening = re.compile(rf"^[}}\t ]*(?:{'|'.join(handlers)})\b")
    bodies: list[list[str]] = []
    margin, inside = 0, False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if opening.match(line):
            opened = line.rsplit("{", 1) if "{" in line else line.rsplit(":", 1)
            bodies.append(opened[1:])
            margin, inside = indent, True
        elif inside and (indent > margin or line.strip() in {"{", ""}):
            bodies[-1].append(line)
        else:
            inside = False
    return bodies


def answers_with_nothing(body: list[str], inert: tuple[str, ...]) -> bool:
    """Whether one handler body states no reaction to the failure it just caught.

    body: the lines the handler clause holds.
    inert: the words a language spells a statement that does nothing with.
    """
    stated = [
        cleaned for line in body if (cleaned := line.split("#")[0].split("//")[0].strip(" \t{};"))
    ]
    return all(word in inert for word in stated)


def binds_only(text: str, name: str) -> bool:
    """Whether one binding names nothing on its left but the given name and a declarator keyword.

    text: the exact source the binding spans.
    name: the name a language reserves for a value nobody wants.
    """
    declarators = frozenset({"let", "const", "var", "val", "mut"})
    stated = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.split("=")[0]))
    return stated - declarators == {name}


@rule
def swallowed_error(
    subject: SyntaxFact,
    *,
    handlers: tuple[str, ...] = ("except", "catch", "rescue"),
    inert: tuple[str, ...] = ("pass", "continue", "..."),
    discard: str = "_",
    failures_as_values: tuple[str, ...] = ("rust", "go"),
) -> Count:
    """Count failures a declaration catches and then answers with nothing.

    Definition
    ----------
    Read every guard one declaration states and report each handler clause whose body does no
    work. An empty body, a lone `pass`, a lone `continue`, and a lone ellipsis all say the same
    thing, which is that the failure was seen and then dropped, so `except ValueError` followed by
    `pass` in Python and an empty `catch {}` in TypeScript or C++ land here together. Where a
    language hands failures back as values rather than throwing them, the same discard is written
    as a binding to the throwaway name, and `let _ = fallible()` in Rust counts for that reason.

    A dropped failure costs far more than the failure itself. Everything after the guard runs on
    state the failed step never finished writing, so the program carries on and produces a wrong
    answer confidently, and the person reading the logs a week later sees a clean run instead of
    the one line that would have named the cause.

    Evidence
    --------
    Each finding names the declaration, the guard, and the handler that answers with nothing. The
    value is the number of failures the declaration throws away.

    Exceptions
    ----------
    A handler that logs, returns a fallback, retries, or raises anything at all has answered the
    failure and is left alone. A comment is not an answer, because the run still carries on as if
    nothing had gone wrong, so a handler holding only a comment is reported. A binding to the
    throwaway name counts only when it throws away the result of a call, since `_ = 3` discards no
    failure, and only where the language returns failures as values, because `_ = risky()` in
    Python or TypeScript drops a value while the exception carries on regardless. A pattern that
    binds other names beside the throwaway, such as `let Some((_, rest)) = split(path)`, is
    destructuring rather than a discard and keeps the part it kept. The inert words, the throwaway
    name, and the languages that return failures are all settings, since a project may spell its
    own no-op and a language MCMR has not met yet may spell either differently. Only a callable is
    judged, because a guard belongs to code that runs and a type reaches every guard it owns
    through the callable holding it, which would otherwise report the same one twice. `handlers`
    names the words a language opens a handler clause with and `failures_as_values` names the
    languages that return failures rather than throwing them, which is what decides whether a
    discard binding is read at all.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           deliver(message)
       except TimeoutError:
           pass

    Good
    ~~~~
    .. code-block:: python

       try:
           deliver(message)
       except TimeoutError:
           logger.warning("delivery timed out, queued for retry", extra=message.trace())
           queue.retry(message)

    References
    ----------
    Generalizes Ruff S110 try-except-pass
    https://docs.astral.sh/ruff/rules/try-except-pass/
    Generalizes Ruff S112 try-except-continue
    https://docs.astral.sh/ruff/rules/try-except-continue/
    Cites "Common Weakness Enumeration", CWE-390, detection of error condition without action
    https://cwe.mitre.org/data/definitions/390.html
    Generalizes Clippy let_underscore_must_use
    https://rust-lang.github.io/rust-clippy/master/index.html#let_underscore_must_use
    Cites "Effective Java", item 77, do not ignore exceptions
    """
    if subject.tree is None or subject.kind != "callable":
        return 0
    swallowed = sum(
        answers_with_nothing(body, inert)
        for guard in subject.tree.of_kind("guard")
        for body in handler_bodies(guard.text, handlers)
    )
    if subject.language not in failures_as_values:
        return swallowed
    thrown_away = [
        binding
        for binding in subject.tree.of_kind("binding")
        if binds_only(binding.text, discard) and binding.of_kind("call")
    ]
    return swallowed + len(thrown_away)
