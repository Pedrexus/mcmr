from ..... import rule
from .....facts import FunctionFact
from .....models import Count


@rule
def function_conditional_count(
    subject: FunctionFact,
) -> Count:
    """Limit explicit `if` branches inside one function or method.

    Definition
    ----------
    Count every `if` and `elif` statement owned by each synchronous or asynchronous callable.
    Nested functions and classes start independent scopes. Return the conditional count for this
    callable. A separate policy can compare the value with a project ceiling such as two.

    Evidence
    --------
    Evidence records the callable source range and its conditional count. This intentionally
    narrower measurement complements cyclomatic complexity. It makes repeated type or mode switches
    visible even when each branch body is small. The value is the number of `if` and `elif`
    statements this callable owns.

    Exceptions
    ----------
    Generated and vendored code may be excluded through globs. Guard clauses, `elif` branches,
    and nested conditionals all count because several independent decisions in one callable are
    still several reasons for it to change. Pattern matching and conditional expressions are not
    `if` statements and remain outside this rule.

    Examples
    --------
    Bad
    ~~~
    A function that checks `BooleanPolicy`, `NumericPolicy`, and `CategoryPolicy` with three
    `isinstance` branches is reported. Replace the closed type switch with one abstract operation
    implemented by concrete policy or evaluator classes. When the operation cannot live on those
    classes, use `functools.singledispatch` to keep type registration open to new implementations.

    Good
    ~~~~
    A base `ResultEvaluator.evaluate` method is abstract. Boolean, numeric, and category evaluator
    subclasses each implement their own policy without inspecting sibling types. A function with
    two cohesive guard conditions remains within the default ceiling.

    References
    ----------
    Cites "Refactoring", Replace Conditional with Polymorphism
    https://refactoring.com/catalog/replaceConditionalWithPolymorphism.html
    Cites "The Python Standard Library", `functools.singledispatch`
    https://docs.python.org/3/library/functools.html#functools.singledispatch
    Cites "Clean Code", chapter 10, Classes
    Cites "Object-Oriented Software Construction", Open Closed Principle
    """
    return subject.conditional_count
