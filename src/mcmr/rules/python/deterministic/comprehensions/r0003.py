from ..... import rule
from .....facts import ComprehensionFact, SetLoopCandidate
from .....models import Count, Remove, Replace, SourceRewrite


def is_convertible(candidate: SetLoopCandidate) -> bool:
    """Whether one initialization and loop pair carries the exact comprehension semantics."""
    return (
        candidate.has_unshadowed_set_initialization
        and candidate.loop_is_synchronous
        and candidate.only_effect_is_add
        and candidate.conditional_count <= 1
        and not candidate.has_else
    )


def comprehension_rewrites(candidate: SetLoopCandidate) -> list[SourceRewrite]:
    """Return the rewrites folding one loop into a comprehension, when every node resolved."""
    initialization, loop = candidate.initialization, candidate.loop
    element, target, iterable = candidate.element, candidate.target, candidate.iterable
    if initialization is None or loop is None or not candidate.name:
        return []
    if element is None or target is None or iterable is None:
        return []
    clauses = "".join(f" if {condition.text}" for condition in candidate.conditions)
    comprehension = f"{{{element.text} for {target.text} in {iterable.text}{clauses}}}"
    return [
        Replace(target=initialization, source=f"{candidate.name} = {comprehension}"),
        Remove(target=loop),
    ]


@rule
def manual_set_comprehension(subject: ComprehensionFact) -> Count:
    """Count fresh sets populated by a loop that can be one set comprehension.

    Definition
    ----------
    Detect a local name initialized by the unshadowed builtin `set()` immediately before a
    synchronous `for` loop. Require the loop's only effect to be `name.add(expression)`, optionally
    inside one `if` without an `else`. Convert that condition directly into the comprehension
    filter. The result is the number of proven candidates. A safe UTF-8 edit replaces the
    initialization and loop when every required expression is available as single-line source.

    Evidence
    --------
    Each finding identifies the fresh set, initialization-to-loop range, and loop line. The safe
    fix preserves a plain or annotated assignment and retains the iterable, target, expression, and
    optional condition in their original evaluation order. The value is the number of loops a set
    comprehension would replace exactly.

    Exceptions
    ----------
    Abstain when `set` is shadowed, the loop is asynchronous, the set already contains values, the
    body has multiple effects, an `else` or control-flow statement exists, or the expression reads
    the set being built. Also abstain inside exception handlers, in module or class scope, when a
    a loop binding is referenced elsewhere in its function, or when assignment expressions,
    `await`, or `yield` make scope and evaluation semantics differ. Attribute-only targets and
    dynamic local-scope introspection also suppress the finding. Comments suppress the automatic
    edit rather than being deleted.

    Examples
    --------
    Bad
    ~~~
    `values = set(); for item in source: values.add(normalize(item))` manually builds a set.
    A body containing only `if item.valid: values.add(item.key)` is the filtered form.

    Good
    ~~~~
    `values = {normalize(item) for item in source}` and
    `values = {item.key for item in source if item.valid}` state the collection directly. A loop
    with logging, an `else`, an async iterator, or later use of `item` remains explicit.

    References
    ----------
    Cites "The Python Tutorial", Sets and set comprehensions
    https://docs.python.org/3.14/tutorial/datastructures.html#sets
    Cites "The Python Language Reference", Displays for lists, sets and dictionaries
    https://docs.python.org/3.14/reference/expressions.html#displays-for-lists-sets-and-dictionaries
    Cites "Fluent Python", chapter 2, An Array of Sequences
    """
    return sum(is_convertible(candidate) for candidate in subject.set_loop_candidates)


@manual_set_comprehension.fix(is_default=True)
def use_set_comprehension(subject: ComprehensionFact) -> list[SourceRewrite]:
    """Build the set in one comprehension and drop the loop that filled it."""
    return [
        rewrite
        for candidate in subject.set_loop_candidates
        if is_convertible(candidate)
        for rewrite in comprehension_rewrites(candidate)
    ]
