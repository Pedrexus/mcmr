from mcmr.facts import (
    AttributeAccess,
    AttributeAccessFact,
    CallFact,
    CallSite,
    Expression,
    LiteralKind,
    MappingEntry,
    NodeRef,
    SourceSpan,
)
from mcmr.models import Replace
from mcmr.rules.python.deterministic.asyncio.r0001 import asyncio_run_boundary
from mcmr.rules.python.deterministic.asyncio.r0003 import deprecated_event_loop_policy_usage
from mcmr.rules.python.deterministic.asyncio.r0004 import default_executor_to_thread_candidate
from mcmr.rules.python.deterministic.asyncio.r0005 import (
    deprecated_asyncio_coroutine_function_check,
    replace_with_inspect,
)
from mcmr.rules.python.deterministic.classes.r0012 import direct_method_descriptor_call_count
from mcmr.rules.python.deterministic.cli.r0001 import argparse_cli_construction
from mcmr.rules.python.deterministic.collections.r0004 import (
    explicit_tuple_construction,
    replace_with_list,
    replace_with_tuple_literal,
)
from mcmr.rules.python.deterministic.enumerations.r0005 import (
    prefer_enum_conversion,
    use_public_conversion,
)
from mcmr.rules.python.deterministic.logging.r0001 import (
    logger_boundary_bypass_count,
    route_through_the_preferred_logger,
)
from mcmr.rules.python.deterministic.performance.r0006 import (
    tensor_interoperability_round_trip_count,
)
from mcmr.rules.python.deterministic.pydantic.r0004 import (
    redundant_model_validate,
    use_model_constructor,
)
from mcmr.rules.python.deterministic.torch.r0001 import (
    fluent_tensor_call_chain,
    use_fluent_tensor_chain,
)

SPAN = SourceSpan(path="src/example.py")


def calls(*items: CallSite, module_bindings: tuple[str, ...] = ()) -> CallFact:
    """Build one resolved call index."""
    return CallFact(
        key="calls",
        span=SPAN,
        calls=list(items),
        module_bindings=list(module_bindings),
        language="python",
    )


def node(identifier: str, text: str = "") -> NodeRef:
    """Build one addressed syntax node for fix assertions."""
    return NodeRef(id=identifier, span=SPAN, text=text)


def test_asyncio_call_cases() -> None:
    running_loop = Expression(text="loop", qualified_name="asyncio.get_running_loop")
    subject = calls(
        CallSite(qualified_name="asyncio.run", path="src/a.py"),
        CallSite(qualified_name="asyncio.get_event_loop_policy", path="src/a.py"),
        CallSite(
            qualified_name="asyncio.iscoroutinefunction",
            path="src/a.py",
            callee=node("callee", "asyncio.iscoroutinefunction"),
        ),
        CallSite(
            qualified_name="loop.run_in_executor",
            path="src/a.py",
            receiver=running_loop,
            arguments=[Expression(text="None"), Expression(text="work"), Expression(text="value")],
        ),
        CallSite(
            qualified_name="loop.run_in_executor",
            path="src/a.py",
            receiver=running_loop,
            arguments=[Expression(text="pool"), Expression(text="work")],
        ),
    )
    assert asyncio_run_boundary(subject) == 1
    assert deprecated_event_loop_policy_usage(subject) == 1
    assert deprecated_event_loop_policy_usage(subject, python_minor=13) == 0
    assert deprecated_asyncio_coroutine_function_check(subject) == 1
    assert deprecated_asyncio_coroutine_function_check(subject, python_minor=13) == 0
    assert default_executor_to_thread_candidate(subject) == 1
    assert default_executor_to_thread_candidate(subject, python_minor=8) == 0

    plan = replace_with_inspect(subject)
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        "inspect.iscoroutinefunction"
    ]
    assert replace_with_inspect(calls()) is None


def test_descriptor_cli_and_tuple_call_cases() -> None:
    construction = CallSite(
        qualified_name="builtins.tuple",
        path="src/a.py",
        arguments=[Expression(text="values")],
        node=node("tuple-call", "tuple(values)"),
    )
    subject = calls(
        CallSite(qualified_name="builtins.staticmethod", path="src/a.py"),
        CallSite(
            qualified_name="builtins.classmethod",
            path="src/a.py",
            is_decorator_factory=True,
        ),
        CallSite(qualified_name="argparse.ArgumentParser", path="src/a.py"),
        construction,
        CallSite(qualified_name="builtins.tuple", path="src/a.py", is_shadowed=True),
    )
    assert direct_method_descriptor_call_count(subject) == 1
    assert argparse_cli_construction(subject) == 1
    assert explicit_tuple_construction(subject) == 1

    as_list = replace_with_list(subject)
    as_literal = replace_with_tuple_literal(subject)
    assert as_list is not None and as_literal is not None
    assert [rewrite.source for rewrite in as_list.rewrites if isinstance(rewrite, Replace)] == [
        "list(values)"
    ]
    assert [rewrite.source for rewrite in as_literal.rewrites if isinstance(rewrite, Replace)] == [
        "(*values,)"
    ]
    assert replace_with_list(calls()) is None
    assert replace_with_tuple_literal(calls()) is None


def test_enum_value_access_cases() -> None:
    subject = AttributeAccessFact(
        key="accesses",
        span=SPAN,
        language="python",
        accesses=[
            AttributeAccess(
                name="value",
                receiver_kind="other",
                receiver_text="Status.ACTIVE",
                receiver_type="Status",
                receiver_type_bases=["StrEnum"],
                node=node("status-value", "Status.ACTIVE.value"),
            ),
            AttributeAccess(
                name="value",
                receiver_kind="other",
                receiver_text="mode",
                receiver_type="Mode",
                receiver_type_bases=["Enum"],
            ),
            AttributeAccess(name="name", receiver_kind="other", receiver_type_bases=["StrEnum"]),
        ],
    )
    assert prefer_enum_conversion(subject) == 1

    plan = use_public_conversion(subject)
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        "str(Status.ACTIVE)"
    ]
    assert use_public_conversion(subject.model_copy(update={"accesses": []})) is None


def test_logging_boundary_cases() -> None:
    bypassing = calls(
        CallSite(qualified_name="logging.info", path="src/a.py"),
        CallSite(qualified_name="common.log.logger", path="src/a.py"),
    )
    assert logger_boundary_bypass_count(bypassing) == 1
    assert (
        logger_boundary_bypass_count(
            bypassing.model_copy(update={"module_bindings": ["common.log.logger"]})
        )
        == 0
    )

    span = SourceSpan(path="src/a.py")
    addressed = calls(
        CallSite(
            qualified_name="logging.warning",
            path="src/a.py",
            callee=NodeRef(id="callee", span=span, text="logging.warning"),
        ),
        CallSite(
            qualified_name="logging.getLogger",
            path="src/a.py",
            callee=NodeRef(id="factory", span=span, text="logging.getLogger"),
        ),
    )
    plan = route_through_the_preferred_logger(addressed)
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        "logger.warning",
        "logger.info",
    ]
    assert route_through_the_preferred_logger(bypassing) is None


def test_tensor_and_model_call_cases() -> None:
    round_trip = CallSite(
        qualified_name="torch.as_tensor",
        path="src/a.py",
        arguments=[
            Expression(
                text="cp.asnumpy(array)",
                qualified_name="cupy.asnumpy",
                arguments=[Expression(text="array")],
            )
        ],
    )
    validated = CallSite(
        qualified_name="User.model_validate",
        path="src/a.py",
        receiver=Expression(text="User"),
        node=node("validate", "User.model_validate({'name': name})"),
        arguments=[
            Expression(
                text="{'name': name}",
                literal_kind=LiteralKind.MAPPING,
                entries=[MappingEntry(key="name", value=Expression(text="name"))],
            )
        ],
    )
    power = CallSite(
        qualified_name="torch.pow",
        path="src/a.py",
        assigned_target="sigma",
        node=node("power", "torch.pow(2.0, torch.round(torch.log2(sigma)))"),
        arguments=[
            Expression(text="2.0", literal_kind=LiteralKind.NUMBER),
            Expression(
                text="torch.round(torch.log2(sigma))",
                qualified_name="torch.round",
                arguments=[
                    Expression(
                        text="torch.log2(sigma)",
                        qualified_name="torch.log2",
                        arguments=[Expression(text="sigma")],
                    )
                ],
            ),
        ],
    )
    subject = calls(
        round_trip,
        CallSite(
            qualified_name="torch.as_tensor",
            path="src/a.py",
            arguments=[Expression(text="array", qualified_name="cupy.ndarray")],
        ),
        validated,
        CallSite(
            qualified_name="User.model_validate",
            path="src/a.py",
            arguments=[Expression(text="payload")],
        ),
        power,
        power.model_copy(update={"is_shadowed": True}),
    )
    assert tensor_interoperability_round_trip_count(subject) == 1
    assert redundant_model_validate(subject) == 1
    assert fluent_tensor_call_chain(subject) == 1
    assert fluent_tensor_call_chain(subject, minimum_operations=4) == 0

    constructor = use_model_constructor(subject)
    chain = use_fluent_tensor_chain(subject)
    assert constructor is not None and chain is not None
    assert [
        rewrite.source for rewrite in constructor.rewrites if isinstance(rewrite, Replace)
    ] == ["User(name=name)"]
    assert [rewrite.source for rewrite in chain.rewrites if isinstance(rewrite, Replace)] == [
        "sigma.log2_().round_().exp2_()"
    ]
    assert use_model_constructor(calls()) is None
    assert use_fluent_tensor_chain(calls()) is None

    borrowed = power.model_copy(update={"assigned_target": "scaled"})
    plan = use_fluent_tensor_chain(calls(borrowed))
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        "sigma.log2().round().exp2()"
    ]

    single = power.model_copy(update={"arguments": [power.arguments[0], Expression(text="sigma")]})
    unknown = power.model_copy(
        update={
            "arguments": [
                power.arguments[0],
                Expression(text="torch.fft(sigma)", qualified_name="torch.fft"),
            ]
        }
    )
    keyword = power.model_copy(update={"keyword_names": ["out"]})
    other_base = power.model_copy(
        update={
            "arguments": [
                Expression(text="3.0", literal_kind=LiteralKind.NUMBER),
                power.arguments[1],
            ]
        }
    )
    assert fluent_tensor_call_chain(calls(other_base)) == 0
    assert fluent_tensor_call_chain(calls(single, unknown, keyword)) == 0
    assert fluent_tensor_call_chain(calls(single), minimum_operations=1) == 1
