from ..... import rule
from .....facts import SyntaxFact
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def uninformative_local_name(subject: SyntaxFact, *, minimum_length: int = 3) -> CountReport:
    """Count local names too short to say what they hold.

    Definition
    ----------
    Read every name one declaration binds and report one shorter than `minimum_length` that is not
    a conventional index or a loop counter. A local name is the cheapest documentation a body has
    and the only one that cannot go stale, so a body that binds `d`, `r`, and `tmp` has spent that
    budget on nothing and made every later line ambiguous.

    Only a callable is judged. A field on a type is part of an interface its readers meet by name
    elsewhere, so `id` on a model reads fine where `id` inside a function body does not.

    This is the first rule to read code rather than counts. It receives the declaration's own tree
    and its exact source, which is what lets it ask about spelling at all.

    Evidence
    --------
    Each finding names the declaration that holds the binding, the name itself, the line it sits
    on, and how many characters short of readable it is. The repair is a choice, because only the
    author knows what the value holds. The value is the number of uninformative bindings.

    Exceptions
    ----------
    A single-letter index in a comprehension or a short loop is a convention older than the code
    and reads fine, so `i`, `j`, `k`, `n`, and `x` through `z` are left alone. A field declared on
    a type is not a local and is not judged. A name whose scope is one line is arguably fine too,
    which is why the ceiling is a setting rather than a rule.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def load(path):
           d = read(path)
           r = parse(d)
           return r

    Good
    ~~~~
    .. code-block:: python

       def load(path):
           raw = read(path)
           return parse(raw)

    References
    ----------
    Cites "Clean Code", chapter 2, meaningful names
    Cites "Code Complete", chapter 11, the power of variable names
    Cites "PEP 8, Style Guide for Python Code", naming conventions
    https://peps.python.org/pep-0008/#naming-conventions
    """
    conventional = frozenset({"i", "j", "k", "n", "x", "y", "z", "_"})
    if subject.tree is None or subject.kind != "callable":
        return Reported(value=0)
    brief = [
        node
        for node in subject.tree.of_kind("binding")
        if node.name and len(node.name) < minimum_length and node.name not in conventional
    ]
    return Reported(
        value=len(brief),
        findings=tuple(
            Finding(
                message=(
                    f"`{subject.qualname}` binds `{node.name}`, which is shorter than the "
                    f"{minimum_length} characters a name needs to say what it holds"
                ),
                span=node.span or subject.span,
                measurements=(
                    Measurement(name="characters in the name", value=len(node.name)),
                    Measurement(name="characters a name needs here", value=minimum_length),
                ),
                repair=Choice(question=f"rename `{node.name}` after what it holds"),
            )
            for node in brief
        ),
    )
