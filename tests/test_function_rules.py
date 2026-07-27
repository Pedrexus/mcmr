from mcmr.facts import FunctionFact, FunctionParameter, NodeRef, SourceSpan, Visibility
from mcmr.models import Inline
from mcmr.rules.general.deterministic.functions.r0001 import function_implementation_lines
from mcmr.rules.general.deterministic.functions.r0002 import (
    inline_trivial_helper,
    single_use_trivial_helper,
)
from mcmr.rules.general.deterministic.functions.r0003 import class_owned_module_helper
from mcmr.rules.general.deterministic.functions.r0008 import (
    inline_one_line_function,
    unnecessary_one_line_concrete_function,
)
from mcmr.rules.general.deterministic.functions.r0009 import (
    inline_transparent_wrapper,
    transparent_unary_wrapper,
)
from mcmr.rules.general.deterministic.functions.r0010 import shallow_callable
from mcmr.rules.general.deterministic.functions.r0011 import function_conditional_count
from mcmr.rules.python.deterministic.asyncio.r0002 import task_group_candidate
from mcmr.rules.python.deterministic.caching.r0001 import (
    instance_independent_cached_property,
)
from mcmr.rules.python.deterministic.caching.r0002 import cached_instance_method
from mcmr.rules.python.deterministic.dead_code.r0001 import (
    remove_unreferenced_private_function,
    unreferenced_private_function,
)
from mcmr.rules.python.deterministic.documentation.r0001 import compact_house_docstring
from mcmr.rules.python.deterministic.documentation.r0002 import tensor_docstring_semantics
from mcmr.rules.python.deterministic.functions.r0004 import (
    unjustified_positional_only_parameter_count,
)


def addressed(subject: FunctionFact) -> FunctionFact:
    """Return the same function with the declaration, body, and references addressed."""
    span = SourceSpan(path="src/service.py")
    return subject.model_copy(
        update={
            "definition": NodeRef(id="definition", span=span, text="def helper(value): ..."),
            "body_expression": NodeRef(id="body", span=span, text="normalize(value)"),
            "references": [NodeRef(id="reference", span=span, text="helper(value)")],
        }
    )


def function(**changes: bool | int | str | list[str] | list[FunctionParameter]) -> FunctionFact:
    """Build one source function fact with selected primitive observations."""
    values: dict[
        str,
        bool | int | str | SourceSpan | list[str] | list[FunctionParameter],
    ] = {
        "key": "function:example",
        "span": SourceSpan(path="example.py"),
        "name": "example",
    }
    return FunctionFact.model_validate(values | changes)


def test_function_measurement_rules_use_structural_counts() -> None:
    subject = function(implementation_lines=31, conditional_count=3)
    assert function_implementation_lines(subject).value == 31
    assert function_conditional_count(subject) == 3


def test_single_use_trivial_helper_cases() -> None:
    candidate = function(
        name="_normalize",
        scope="module",
        visibility=Visibility.PRIVATE,
        implementation_lines=1,
        direct_statement_count=1,
        reference_count=1,
    )
    assert single_use_trivial_helper(candidate) == 1
    assert single_use_trivial_helper(candidate.model_copy(update={"reference_count": 2})) == 0
    assert single_use_trivial_helper(candidate, ignore_names=("_normalize",)) == 0

    plan = inline_trivial_helper(addressed(candidate))
    assert plan is not None
    assert [rewrite.kind for rewrite in plan.rewrites] == ["inline"]
    assert inline_trivial_helper(candidate) is None


def test_class_owned_helper_cases() -> None:
    candidate = function(
        name="_parse",
        scope="module",
        visibility=Visibility.PRIVATE,
        implementation_lines=2,
        reference_count=1,
        sole_reference_owner_class="Client",
    )
    assert class_owned_module_helper(candidate) == 1
    assert (
        class_owned_module_helper(candidate.model_copy(update={"sole_reference_owner_class": ""}))
        == 0
    )


def test_nested_one_line_function_cases() -> None:
    candidate = function(
        scope="nested",
        implementation_lines=1,
        reference_count=1,
    )
    assert unnecessary_one_line_concrete_function(candidate) == 1
    assert (
        unnecessary_one_line_concrete_function(
            candidate.model_copy(update={"is_first_class_reference": True})
        )
        == 0
    )

    plan = inline_one_line_function(addressed(candidate))
    assert plan is not None
    assert [
        rewrite.declaration.text for rewrite in plan.rewrites if isinstance(rewrite, Inline)
    ] == ["def helper(value): ..."]
    assert inline_one_line_function(candidate) is None


def test_transparent_wrapper_cases() -> None:
    candidate = function(
        scope="module",
        visibility=Visibility.PUBLIC,
        parameters=[FunctionParameter(name="value")],
        direct_statement_count=1,
        returns_single_call=True,
        forwards_only_parameter_unchanged=True,
    )
    assert transparent_unary_wrapper(candidate) == 1
    assert transparent_unary_wrapper(candidate.model_copy(update={"is_async": True})) == 0

    plan = inline_transparent_wrapper(addressed(candidate))
    assert plan is not None
    assert [rewrite.body.text for rewrite in plan.rewrites if isinstance(rewrite, Inline)] == [
        "normalize(value)"
    ]
    assert inline_transparent_wrapper(candidate) is None


def test_shallow_callable_cases() -> None:
    candidate = function(
        scope="method",
        visibility=Visibility.PUBLIC,
        implementation_lines=1,
        behavior_operation_count=1,
        reference_count=1,
    )
    assert shallow_callable(candidate) == 1
    assert shallow_callable(candidate.model_copy(update={"behavior_operation_count": 3})) == 0


def test_python_parameter_contract_cases() -> None:
    subject = function(
        parameters=[
            FunctionParameter(name="value", is_positional_only=True),
            FunctionParameter(
                name="self",
                is_positional_only=True,
                is_receiver=True,
            ),
            FunctionParameter(name="timeout", has_boolean_default=True),
            FunctionParameter(name="retries", is_keyword_only=True),
        ]
    )
    assert unjustified_positional_only_parameter_count(subject) == 1


def test_structured_concurrency_candidate_cases() -> None:
    subject = function(
        is_async=True,
        created_task_count=2,
        gather_consumes_created_tasks=True,
    )
    assert task_group_candidate(subject) == 1
    assert task_group_candidate(subject.model_copy(update={"has_task_group": True})) == 0
    assert (
        task_group_candidate(subject.model_copy(update={"gather_returns_exceptions": True})) == 0
    )


def test_cache_ownership_cases() -> None:
    cached_property = function(
        scope="method",
        cache_decorator="cached_property",
        direct_statement_count=1,
    )
    assert instance_independent_cached_property(cached_property) == 1
    assert (
        instance_independent_cached_property(
            cached_property.model_copy(update={"reads_receiver": True})
        )
        == 0
    )
    cached_method = function(scope="method", cache_decorator="cache")
    assert cached_instance_method(cached_method) == 1
    assert cached_instance_method(cached_method.model_copy(update={"scope": "module"})) == 0


def test_docstring_contract_cases() -> None:
    good = function(docstring="Encode text.\n\ntext: Input text.")
    assert compact_house_docstring(good).value == 0
    assert compact_house_docstring(good.model_copy(update={"docstring": "Encode text"})).value == 1
    assert (
        compact_house_docstring(
            good.model_copy(update={"docstring": "Encode text.\n\nArgs:\n    text: input"})
        ).value
        == 1
    )
    assert compact_house_docstring(good.model_copy(update={"docstring": ""})).value == 0


def test_tensor_documentation_cases() -> None:
    subject = function(
        recognized_tensor_roles=["input", "return"],
        has_tensor_shape_semantics=True,
    )
    assert tensor_docstring_semantics(subject) == 1
    assert (
        tensor_docstring_semantics(subject.model_copy(update={"has_tensor_dtype_semantics": True}))
        == 0
    )


def test_unreferenced_private_function_cases() -> None:
    subject = function(scope="module", visibility=Visibility.PRIVATE, reference_count=0)
    assert unreferenced_private_function(subject) == 1
    assert unreferenced_private_function(subject.model_copy(update={"reference_count": 1})) == 0
    recursive = subject.model_copy(update={"reference_count": 1, "is_recursive": True})
    assert unreferenced_private_function(recursive) == 1
    assert unreferenced_private_function(subject.model_copy(update={"decorators": ["rule"]})) == 0

    plan = remove_unreferenced_private_function(addressed(subject))
    assert plan is not None
    assert [rewrite.kind for rewrite in plan.rewrites] == ["remove"]
    assert remove_unreferenced_private_function(subject) is None
