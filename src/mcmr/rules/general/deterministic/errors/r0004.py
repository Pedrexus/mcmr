import re

from ..... import rule
from .....facts import SyntaxFact, SyntaxNode
from .....models import Count


def thrown_in_its_own_flow(region: SyntaxNode) -> set[str]:
    """Return the error names one region raises where it runs, skipping any type it declares.

    region: the node whose own control flow is being read.
    """
    thrown: set[str] = set()
    for child in region.children:
        if child.kind == "raise":
            thrown.update(
                node.name.rsplit(".", 1)[-1] for node in child.of_kind("call", "name")[:1]
            )
        elif child.kind not in {"callable", "type"}:
            thrown |= thrown_in_its_own_flow(child)
    return thrown


def caught_types(text: str, handlers: tuple[str, ...]) -> list[set[str]]:
    """Return the error names each handler clause of one guard catches, one set per clause.

    text: the exact source the guard spans, as the frontend read it.
    handlers: the words a language opens a handler clause with.
    """
    opening = re.compile(rf"^[}}\t ]*(?:{'|'.join(handlers)})\b")
    caught: list[set[str]] = []
    for line in text.splitlines():
        if opening.match(line):
            stated = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line.split(" as ")[0])
            named = stated if line.rstrip().endswith(":") or len(stated) == 1 else stated[:-1]
            caught.append(set(named) - {*handlers, "const", "final"})
    return caught


@rule
def raise_inside_guarded_region(
    subject: SyntaxFact,
    *,
    handlers: tuple[str, ...] = ("except", "catch", "rescue"),
    catch_all: tuple[str, ...] = ("Exception", "BaseException", "Error", "Throwable"),
) -> Count:
    """Count guards that catch a failure their own protected region threw.

    Definition
    ----------
    Read every guard one declaration states, take the error names its own protected region raises,
    and report the guard when one of its handler clauses would catch one of them. A clause catches
    it when it names that error, when it names a base error such as `Exception` or `Error`, or when
    it names no type at all the way a bare `except` and a JavaScript `catch (error)` do. A raise
    written there is a jump to a handler a few lines below, which is a goto wearing the clothes of
    error handling, and the reader has to hold the whole region in mind to work out where control
    lands.

    The handler pays for it twice. It now answers both the failures the protected calls throw and
    the ones the body threw at itself, so it cannot recover from one without pretending to recover
    from the other, and a real failure from a real call arrives looking exactly like the check the
    body performed on purpose. Moving the check into the function that owns it leaves the guard
    protecting only calls it does not control, which is the one thing a guard is good at.

    Evidence
    --------
    Each finding names the declaration and the guard whose own body raises. The value is the
    number of guards that catch what they threw.

    Exceptions
    ----------
    A raise no clause would catch leaves the guard entirely and is left alone, which is why the
    names are compared at all rather than any raise in the region being reported. Comparing them
    lexically is what a reader does too, and a clause that catches a subclass by a name the raise
    never states is missed rather than guessed at. A guard that states no handler is how a language
    spells cleanup that always runs, and since it catches nothing it is never judged. A raise
    inside a callable the region declares is the very shape this rule asks for, so it is not
    counted even though it is written inside the region. A guard nested inside another is judged on
    its own, and both are reported when both could catch what the inner body threw. Only a callable
    is judged, because a type reaches every guard it owns through the callable holding it and would
    otherwise report the same one twice. `handlers` names the words a language opens a handler
    clause with and `catch_all` names the base errors a clause catches everything through, so a
    project whose own root error is caught that widely adds it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           record = fetch(key)
           if record.expired:
               raise StaleRecord(key)
       except StaleRecord:
           record = rebuild(key)

    Good
    ~~~~
    .. code-block:: python

       def fresh(key):
           record = fetch(key)
           if record.expired:
               raise StaleRecord(key)
           return record

       try:
           record = fresh(key)
       except StaleRecord:
           record = rebuild(key)

    References
    ----------
    Generalizes Ruff TRY301 raise-within-try
    https://docs.astral.sh/ruff/rules/raise-within-try/
    Cites "tryceratops documentation", the linter this check came from
    https://github.com/guilatrova/tryceratops
    Cites "Clean Code", chapter 7, error handling
    Cites "Refactoring", extract function
    """
    if subject.tree is None or subject.kind != "callable":
        return 0
    return sum(
        any(
            not clause or clause & thrown or clause.intersection(catch_all)
            for clause in caught_types(guard.text, handlers)
        )
        for guard in subject.tree.of_kind("guard")
        if (thrown := thrown_in_its_own_flow(guard))
    )
