import re

from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


def handler_clauses(text: str, handlers: tuple[str, ...]) -> list[tuple[str, list[str]]]:
    """Return every handler clause of one guard as the line that opens it and the lines it holds.

    text: the exact source the guard spans, as the frontend read it.
    handlers: the words a language opens a handler clause with.
    """
    opening = re.compile(rf"^[}}\t ]*(?:{'|'.join(handlers)})\b")
    clauses: list[tuple[str, list[str]]] = []
    margin, inside = 0, False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if opening.match(line):
            opened = line.rsplit("{", 1) if "{" in line else line.rsplit(":", 1)
            clauses.append((line, opened[1:]))
            margin, inside = indent, True
        elif inside and (indent > margin or line.strip() in {"{", ""}):
            clauses[-1][1].append(line)
        else:
            inside = False
    return clauses


def caught_name(header: str) -> str:
    """Return the name one handler clause gives the failure it caught, when it states one.

    header: the line that opens the clause, such as `except OSError as error:`.
    """
    if " as " in header:
        return header.split(" as ")[-1].strip(" :{)")
    declared = re.search(r"\((.+)\)", header)
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", declared.group(1)) if declared else []
    return names[-1] if names and not header.rstrip().endswith(":") else ""


def raise_statements(body: list[str], raises: tuple[str, ...]) -> list[str]:
    """Return each raise one handler body states, joined with the lines it runs onto.

    body: the lines the handler clause holds.
    raises: the words a language raises a failure with.
    """
    opening = re.compile(rf"^[\t ]*(?:{'|'.join(raises)})\b")
    statements: list[str] = []
    for line in body:
        if opening.match(line):
            statements.append(line.strip())
        elif statements and statements[-1].count("(") > statements[-1].count(")"):
            statements[-1] += " " + line.strip()
    return statements


@rule
def raise_without_cause(
    subject: SyntaxFact,
    *,
    handlers: tuple[str, ...] = ("except", "catch", "rescue"),
    raises: tuple[str, ...] = ("raise", "throw"),
    causes: tuple[str, ...] = ("from", "cause"),
) -> Count:
    """Count errors raised inside a handler that arrive without the failure they replace.

    Definition
    ----------
    Read every guard one declaration states and report a raise written inside a handler clause
    whose own text names neither the failure that clause caught nor a marker that carries a cause.
    Translating a low level failure into one the caller understands is good practice, and it stays
    good practice only while the new error carries the old one, because the stack that names what
    actually broke lives on the failure being replaced. Python spells the carry as `from error`,
    JavaScript as the `cause` option, Java by handing the caught error to the constructor, and Go
    by wrapping with `%w`. A raise a formatter wrapped over several lines is read through to the
    parenthesis that closes it, so the cause still counts wherever it was written.

    Losing that stack costs a whole debugging session. The report says the profile could not be
    read and never says the disk was full, so whoever is holding the incident has to reproduce
    from scratch what the program already knew and then threw away.

    Evidence
    --------
    Each finding names the declaration, the handler clause, and the raise that arrives with no
    cause. The value is the number of raises that drop what they replace.

    Exceptions
    ----------
    A raise that states a cause marker or names the caught failure itself is carrying the original
    and is left alone. Deliberately breaking the chain with `raise ... from None` says so in the
    source, and it reads as carried for exactly that reason. A bare re-raise names no new error at
    all and hands the original straight on, so it is never judged, and neither is a raise outside a
    handler because it replaces nothing. A handler that binds no name is judged on the markers
    alone, since there is no name a raise there could carry. Only a callable is judged, because a
    type reaches every handler it owns through the callable holding it and would otherwise report
    the same raise twice. `handlers` names the words a language opens a handler clause with,
    `raises` the words it raises with, and `causes` the markers that carry one, so a language
    spelling any of them differently is configured rather than reimplemented.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           profile = read(path)
       except OSError as error:
           raise ConfigurationError("the profile is unreadable")

    Good
    ~~~~
    .. code-block:: python

       try:
           profile = read(path)
       except OSError as error:
           raise ConfigurationError("the profile is unreadable") from error

    References
    ----------
    Generalizes Ruff B904 raise-without-from-inside-except
    https://docs.astral.sh/ruff/rules/raise-without-from-inside-except/
    Cites "PEP 3134, Exception Chaining and Embedded Tracebacks"
    https://peps.python.org/pep-3134/
    Cites "MDN Web Docs", the Error cause option
    https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error/cause
    Cites "The Go documentation", error wrapping with the `%w` verb
    https://go.dev/blog/go1.13-errors
    Cites "Effective Java", item 73, throw exceptions appropriate to the abstraction
    """
    if subject.tree is None or subject.kind != "callable":
        return 0
    return sum(
        {*causes, caught_name(header)}.isdisjoint(stated)
        for guard in subject.tree.of_kind("guard")
        for header, body in handler_clauses(guard.text, handlers)
        for statement in raise_statements(body, raises)
        if len(stated := re.findall(r"[A-Za-z_][A-Za-z0-9_]*", statement)) > 1
    )
