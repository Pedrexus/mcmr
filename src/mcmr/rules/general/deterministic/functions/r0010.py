from ..... import rule
from .....facts import FunctionFact, Visibility


@rule
def shallow_callable(
    subject: FunctionFact,
    *,
    minimum_references: int = 2,
    minimum_operations: int = 3,
    ignore_names: tuple[str, ...] = (),
) -> bool:
    """Detect a one-line public callable without enough behavior or reuse.

    Definition
    ----------
    Inspect public module functions and methods across the project after removing an optional
    docstring. Report a callable with one physical implementation line when it contains fewer than
    `minimum_operations` behavior operations and has fewer than `minimum_references` project
    references. The default requires three operations. Behavior
    operations include calls, comparisons, boolean and arithmetic expressions, comprehensions,
    conditional expressions, assignment expressions, awaiting, and yielding.

    Evidence
    --------
    Each finding records the physical implementation line count, behavior operation count, project
    reference count, complete source range, and sole statement kind. The rule measures reference
    loads by name, so it can conservatively miss a method when unrelated classes reuse the same
    method name. `ALL-FUNC0009` separately owns exact unary forwarding wrappers.

    Exceptions
    ----------
    Private module helpers and nested functions remain owned by their focused rules. Protocol,
    abstract, property, overload, special, framework-decorated, framework lifecycle, and
    structurally proven polymorphic methods are excluded. Valid `ast.NodeVisitor` callbacks are
    also contracts. Pydantic's `model_post_init` is a lifecycle contract rather than a helper.
    `classmethod` and `staticmethod` do not create an exception by themselves. Configure
    `ignore_names` only for a required external boundary that cannot express more behavior.

    Examples
    --------
    Bad
    ~~~
    `main` only calls `app()`. An asynchronous `complete` method only awaits a result and forwards
    it into `record`. Neither boundary adds enough behavior or demonstrated reuse.

    Good
    ~~~~
    `accepts` combines `inspect.isfunction(candidate)` and `inspect.isclass(candidate)`, so its
    one return statement contains more than one behavior operation. A small parser reused from
    several project sites can also retain its named boundary.

    References
    ----------
    Cites "Refactoring", Inline Function
    https://refactoring.com/catalog/inlineFunction.html
    Cites "A Philosophy of Software Design", chapter 4, deep and shallow modules
    Cites "Clean Code", chapter 3, function abstraction levels
    """
    is_exempt = (
        subject.visibility is not Visibility.PUBLIC
        or subject.scope == "nested"
        or subject.is_protocol_member
        or subject.is_abstract
        or subject.is_property
        or subject.is_overload
        or subject.is_protocol_name
        or subject.is_framework_hook
        or subject.is_polymorphic
        or subject.name in ignore_names
    )
    return (
        subject.implementation_lines == 1
        and subject.behavior_operation_count < minimum_operations
        and subject.reference_count < minimum_references
        and not is_exempt
    )
