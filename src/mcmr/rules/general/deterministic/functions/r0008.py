from ..... import rule
from .....facts import FunctionFact
from .....models import FixSafety, Inline, SourceRewrite


@rule
def unnecessary_one_line_concrete_function(
    subject: FunctionFact,
    *,
    minimum_references: int = 2,
) -> bool:
    """Find one-line nested functions whose named boundary lacks demonstrated reuse.

    Definition
    ----------
    Inspect nested functions whose complete reference scope is statically visible. Omit an optional
    docstring and count nonblank, non-comment physical lines in the executable body. Report a
    concrete nested function with exactly one implementation line when direct calls remain below
    `minimum_references`, which defaults to two. Public module functions and methods remain public
    boundaries because repository references cannot disprove external callers or dynamic dispatch.

    Evidence
    --------
    Each finding identifies the definition, structural role, one-line measurement, project
    reference count, and every matching reference location. The result value is the number of
    shallow concrete boundaries that lack the configured reuse evidence.

    Exceptions
    ----------
    Properties, abstract methods, Protocol contracts, overloaded APIs and implementations, special
    methods, recursion, `pass` or ellipsis bodies, and `NotImplementedError` placeholders are
    excluded. A nested function passed as a first-class callable is retained because it cannot be
    replaced by its expression. Functions meeting the reuse threshold remain as named boundaries.
    ALL-FUNC0002 exclusively owns private module helpers, while Vulture owns unused private
    functions.

    Examples
    --------
    A nested `normalize` called once and containing only `return value.strip()` is reported even
    when a long docstring precedes the return. The same function used at two call sites is
    accepted. A callback passed to `map`, public API, one-line property, abstract method, or
    overload implementation is accepted regardless of visible repository reuse.

    References
    ----------
    Cites "Refactoring", Inline Function
    https://refactoring.com/catalog/inlineFunction.html
    Cites "A Philosophy of Software Design", chapter 4, deep and shallow modules
    Cites "The Python Language Reference", special method names
    https://docs.python.org/3/reference/datamodel.html#special-method-names
    Cites "Python typing specification", Protocols
    https://typing.python.org/en/latest/spec/protocol.html
    Cites "Python typing specification", overloads
    https://typing.python.org/en/latest/spec/overload.html
    """
    is_exempt = (
        subject.is_property
        or subject.is_abstract
        or subject.is_protocol_member
        or subject.is_overload
        or subject.is_protocol_name
        or subject.is_recursive
        or subject.is_first_class_reference
        or subject.is_pass_body
        or subject.is_raise_body
    )
    return (
        subject.scope == "nested"
        and subject.implementation_lines == 1
        and subject.reference_count < minimum_references
        and not is_exempt
    )


@unnecessary_one_line_concrete_function.fix(is_default=True, safety=FixSafety.REVIEW)
def inline_one_line_function(
    subject: FunctionFact, *, minimum_references: int = 2
) -> list[SourceRewrite]:
    """Replace each reference with the one line it stands for, then delete the declaration."""
    if subject.definition is None or subject.body_expression is None or not subject.references:
        return []
    return [
        Inline(
            declaration=subject.definition,
            body=subject.body_expression,
            references=subject.references,
        )
    ]
