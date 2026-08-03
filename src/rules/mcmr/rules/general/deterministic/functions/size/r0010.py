import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import FunctionFact
from ......query import FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0006")
def shallow_callable(
    subject: Table[FunctionFact],
    *,
    minimum_references: NonNegativeInt = 2,
    minimum_operations: NonNegativeInt = 1,
    ignore_names: tuple[str, ...] = (),
) -> RuleQuery[bool]:
    """Detect a one-line public callable with no behavior or reuse.

    Definition
    ----------
    Inspect undocumented public Python module functions after removing an optional docstring.
    Report a callable with one physical implementation line when it contains fewer than
    `minimum_operations` behavior operations and has fewer than `minimum_references` project
    references. The default requires one operation. Behavior
    operations include calls, comparisons, boolean and arithmetic expressions, comprehensions,
    conditional expressions, assignment expressions, awaiting, and yielding.

    Evidence
    --------
    Each finding records the physical implementation line count, behavior operation count, project
    reference count, complete source range, and sole statement kind. The rule measures reference
    loads by name, so it can conservatively miss a method when unrelated classes reuse the same
    method name. `ALL-FUNC0005` separately owns exact unary forwarding wrappers.

    Exceptions
    ----------
    Private helpers, nested functions, methods, stubs, tests, and documented public boundaries
    remain owned by their focused rules. Protocol, abstract, overload, framework lifecycle, and
    structurally proven polymorphic functions are excluded. Configure `ignore_names` only for a
    required external boundary that cannot express more behavior.

    Examples
    --------
    Bad
    ~~~
    `answer` only returns a literal and nothing reaches it. Its public boundary adds no behavior or
    demonstrated reuse.

    Good
    ~~~~
    `accepts` calls `inspect.isfunction(candidate)`, so its one return statement performs a real
    operation. A small parser reused from several project sites can also retain its named boundary.

    References
    ----------
    Cites "Refactoring", Inline Function
    https://refactoring.com/catalog/inlineFunction.html
    Cites "A Philosophy of Software Design", chapter 4, deep and shallow modules
    Cites "Clean Code", chapter 3, function abstraction levels
    """
    frame = subject.lazy(FunctionRelation.FUNCTIONS)
    is_exempt = (
        (pl.col("language") != "python")
        | (pl.col("visibility") != "public")
        | (pl.col("scope") != "module")
        | (pl.col("docstring") != "")
        | pl.col("is_protocol_member")
        | pl.col("is_abstract")
        | pl.col("is_property")
        | pl.col("is_overload")
        | pl.col("is_protocol_name")
        | pl.col("is_framework_hook")
        | pl.col("is_polymorphic")
        | pl.col("is_pass_body")
        | pl.col("is_raise_body")
        | pl.col("path").str.ends_with(".pyi")
        | pl.col("name").str.starts_with("test_")
        | pl.col("name").is_in(list(ignore_names))
    )
    value = (
        (pl.col("implementation_lines") == 1)
        & (pl.col("behavior_operation_count") < minimum_operations)
        & (pl.col("reference_count") < minimum_references)
        & ~is_exempt
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "shallow callable"),
    )
