from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    AttributeAccess,
    AttributeAccessFact,
    CallFact,
    NodeRef,
    ReceiverKind,
    SourceSpan,
)
from mcmr.query import RuleQuery
from mcmr.rules.python import (
    argparse_cli_construction,
    asyncio_run_boundary,
    default_executor_to_thread_candidate,
    deprecated_asyncio_coroutine_function_check,
    deprecated_event_loop_policy_usage,
    direct_method_descriptor_call_count,
    explicit_tuple_construction,
    fluent_tensor_call_chain,
    logger_boundary_bypass_count,
    prefer_enum_conversion,
    redundant_model_validate,
    tensor_interoperability_round_trip_count,
)
from mcmr.table import AnalysisSession

from ..support import retained_query

if TYPE_CHECKING:
    from pathlib import Path

    from mcmr.plugins import Fact, Table


def repository(root: Path) -> Path:
    """Write one call corpus covering values and embedded query fixes."""
    (root / "subject.py").write_text(
        """import argparse
import asyncio
import logging

import cupy as cp
import torch
from pydantic import BaseModel


class User(BaseModel):
    name: str


async def work(value: int = 1) -> int:
    return value


def calls(array, sigma, name):
    asyncio.run(work())
    asyncio.get_event_loop_policy()
    asyncio.iscoroutinefunction(work)
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, work, 1)
    staticmethod(work)
    argparse.ArgumentParser()
    tuple([name, sigma])
    tuple(item for item in [name, sigma])
    frozenset([name, sigma])
    logging.warning("warning")
    torch.as_tensor(cp.asnumpy(array))
    User.model_validate({"name": name})
    sigma = torch.pow(2.0, torch.round(torch.log2(sigma)))
    return sigma
""",
        encoding="utf-8",
    )
    return root


def call_table(root: Path) -> Table[CallFact]:
    """Parse the call corpus into specialized typed relations."""
    return AnalysisSession(
        repository(root),
        suffixes=[".py"],
        typed_families=[CallFact],
    ).call_tables()


def query(
    table: Table[CallFact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one call rule once over all calls."""
    result = rule.invoke_table(
        cast("Table[Fact]", table),
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic test rule returned a model query")
    return result


def total(
    table: Table[CallFact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the single corpus scalar after one table-rule invocation."""
    rows = query(table, rule, **settings).values.collect()
    for column in ("boolean_value", "integer_value", "float_value", "category_value"):
        values = rows.get_column(column).drop_nulls()
        if values.len() == 1:
            return cast("RuleValue", values.item())
    raise TypeError("the rule emitted no scalar value")


def test_asyncio_call_queries_keep_version_gates_and_fixes(tmp_path: Path) -> None:
    table = call_table(tmp_path)
    cases = [
        (asyncio_run_boundary, {}, 1),
        (deprecated_event_loop_policy_usage, {}, 1),
        (deprecated_event_loop_policy_usage, {"python_minor": 13}, 0),
        (deprecated_asyncio_coroutine_function_check, {}, 1),
        (deprecated_asyncio_coroutine_function_check, {"python_minor": 13}, 0),
        (default_executor_to_thread_candidate, {}, 1),
        (default_executor_to_thread_candidate, {"python_minor": 8}, 0),
    ]
    assert [total(table, rule, **settings) for rule, settings, _ in cases] == [
        expected for _, _, expected in cases
    ]

    result = query(table, deprecated_asyncio_coroutine_function_check)
    assert result.fix is not None
    assert result.fix.rewrites.collect().get_column("source").to_list() == [
        "inspect.iscoroutinefunction"
    ]


def test_call_queries_keep_structural_values_and_exact_fix_sources(tmp_path: Path) -> None:
    table = call_table(tmp_path)
    expected: dict[RuleContract, int] = {
        direct_method_descriptor_call_count: 1,
        argparse_cli_construction: 1,
        explicit_tuple_construction: 3,
        logger_boundary_bypass_count: 1,
        tensor_interoperability_round_trip_count: 1,
        redundant_model_validate: 1,
        fluent_tensor_call_chain: 1,
    }
    for rule, count in expected.items():
        assert total(table, rule) == count

    fixes = {
        explicit_tuple_construction: ["[name, sigma]"],
        logger_boundary_bypass_count: ["logger.warning"],
        redundant_model_validate: ["User(name=name)"],
        fluent_tensor_call_chain: ["sigma.log2_().round_().exp2_()"],
    }
    for rule, sources in fixes.items():
        result = query(table, rule)
        assert result.fix is not None
        assert result.fix.rewrites.collect().get_column("source").to_list() == sources


def test_enum_value_access_query_keeps_public_conversion_fix() -> None:
    span = SourceSpan(path="src/example.py")
    subject = AttributeAccessFact(
        key="accesses",
        span=span,
        language="python",
        accesses=[
            AttributeAccess(
                name="value",
                receiver_kind=ReceiverKind.OTHER,
                receiver_text="Status.ACTIVE",
                receiver_type="Status",
                receiver_type_bases=["StrEnum"],
                node=NodeRef(id="status-value", span=span, text="Status.ACTIVE.value"),
            ),
            AttributeAccess(
                name="value",
                receiver_kind=ReceiverKind.OTHER,
                receiver_text="mode",
                receiver_type="Mode",
                receiver_type_bases=["Enum"],
                node=NodeRef(id="mode-value", span=span),
            ),
        ],
    )
    result = retained_query(subject, prefer_enum_conversion)
    assert result.values.collect().item(0, "integer_value") == 1
    assert result.fix is not None
    assert result.fix.rewrites.collect().get_column("source").to_list() == ["str(Status.ACTIVE)"]


def test_one_call_rule_invocation_covers_the_whole_file(tmp_path: Path) -> None:
    table = call_table(tmp_path)
    result = query(table, asyncio_run_boundary)
    assert result.values.collect().height == 1
