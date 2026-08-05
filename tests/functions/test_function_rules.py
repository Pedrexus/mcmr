from typing import TYPE_CHECKING

import polars as pl

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import FunctionFact
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import (
    class_owned_module_helper,
    function_conditional_count,
    function_statement_count,
    shallow_callable,
    single_use_trivial_helper,
    transparent_unary_wrapper,
    unnecessary_one_line_concrete_function,
)
from mcmr.rules.python import (
    cached_instance_method,
    compact_house_docstring,
    instance_independent_cached_property,
    task_group_candidate,
    tensor_docstring_semantics,
    unjustified_positional_only_parameter_count,
    unreferenced_private_function,
)
from mcmr.table import AnalysisSession, FunctionRelation

if TYPE_CHECKING:
    from pathlib import Path

    from mcmr.plugins import Table


def repository(root: Path) -> Path:
    """Write one source corpus whose function facts cover values and query fixes."""
    (root / "service.py").write_text(
        '''import asyncio
from functools import cache, cached_property
from typing import Protocol

import torch


def _unused() -> int:
    return 1


def _normalize(value: int) -> int:
    return int(value)


def use_normalize(value: int) -> int:
    return _normalize(value)


def _prepare(value: str) -> str:
    prepared = value.strip()
    return prepared.casefold()


def wrapper(value: int) -> int:
    return int(value)


def answer() -> int:
    return 1


@rule("EXAMPLE")
def declarative(subject):
    return subject.lazy("facts")


def conditional(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def positional(value: int = 1, /) -> int:
    return value


def documented(value: int) -> int:
    """Return a value.

    value: Input value.
    """
    return value


def documented_directive(value: int) -> int:
    """Return a value.

    .. code-block:: python

       documented_directive(1)
       package::documented_directive(1)
    """
    return value


def undocumented(value: int) -> int:
    """Return a value"""
    return value


def tensor(value: torch.Tensor) -> torch.Tensor:
    """Transform one tensor."""
    return value


async def work() -> int:
    return 1


async def concurrent() -> list[int]:
    first = asyncio.create_task(work())
    second = asyncio.create_task(work())
    return await asyncio.gather(first, second)


def outer(value: int) -> int:
    def inner(item: int) -> int:
        return item + 1

    return inner(value)


class Cache:
    def prepare(self, value: str) -> str:
        return _prepare(value)

    @cached_property
    def version(self) -> int:
        return 1

    @cache
    def compute(self, value: int) -> int:
        return value


class Reader(Protocol):
    def read1(self, size=-1, /) -> bytes: ...
''',
        encoding="utf-8",
    )
    return root


def function_table(root: Path) -> Table[FunctionFact]:
    """Parse the function corpus into its specialized typed relations."""
    return AnalysisSession(
        repository(root),
        suffixes=[".py"],
        typed_families=[FunctionFact],
    ).function_tables()


def query(
    table: Table[FunctionFact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one function rule once over the whole table."""
    result = rule.invoke_table(
        table,
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic test rule returned a model query")
    return result


def fact_id(table: Table[FunctionFact], name: str) -> str:
    """Return the stable identity of one named function row."""
    rows = table.frame(FunctionRelation.FUNCTIONS).filter(
        table.frame(FunctionRelation.FUNCTIONS)["name"] == name
    )
    identity = rows.item(0, "fact_id")
    if not isinstance(identity, str):
        raise TypeError("a function row has no string fact identity")
    return identity


def value(
    table: Table[FunctionFact],
    rule: RuleContract,
    name: str,
    **settings: RuleSetting,
) -> RuleValue:
    """Return one named function's scalar from a rule invoked once."""
    values = query(table, rule, **settings).values.collect()
    rows = values.filter(values["fact_id"] == fact_id(table, name))
    return scalar_frame_value(rows)


def test_function_measurements_and_predicates_use_native_rows(tmp_path: Path) -> None:
    table = function_table(tmp_path)
    statements = query(table, function_statement_count).values.collect()
    assert fact_id(table, "declarative") not in statements["fact_id"].to_list()
    cases = [
        (function_statement_count, "conditional", {}, 3),
        (function_conditional_count, "conditional", {}, 2),
        (single_use_trivial_helper, "_normalize", {}, 1),
        (single_use_trivial_helper, "_normalize", {"maximum_lines": 0}, 0),
        (transparent_unary_wrapper, "wrapper", {}, 1),
        (shallow_callable, "wrapper", {}, 0),
        (shallow_callable, "answer", {}, 1),
        (unnecessary_one_line_concrete_function, "inner", {}, 1),
    ]
    assert [value(table, rule, name, **settings) for rule, name, settings, _ in cases] == [
        expected for _, _, _, expected in cases
    ]


def test_unreferenced_function_query_keeps_its_remove_program(tmp_path: Path) -> None:
    table = function_table(tmp_path)
    result = query(table, unreferenced_private_function)

    assert result.fix is not None
    rewrites = result.fix.rewrites.collect()
    selected = rewrites.filter(rewrites["fact_id"] == fact_id(table, "_unused"))
    assert selected.get_column("kind").to_list() == ["remove"]


def test_single_use_helper_query_keeps_its_inline_program(tmp_path: Path) -> None:
    table = function_table(tmp_path)
    inline = query(table, single_use_trivial_helper)

    assert inline.fix is not None
    normalize_id = fact_id(table, "_normalize")
    rewrites = inline.fix.rewrites.collect()
    nodes = inline.fix.nodes.collect()

    assert rewrites.filter(rewrites["fact_id"] == normalize_id).get_column("kind").to_list() == [
        "inline"
    ]
    assert nodes.filter(nodes["fact_id"] == normalize_id).get_column("role").to_list() == [
        "body",
        "declaration",
        "reference",
    ]


def test_class_owned_helper_query_keeps_its_move_and_call_replacement(tmp_path: Path) -> None:
    """The review plan owns both halves of moving one helper into its class."""
    table = function_table(tmp_path)
    result = query(table, class_owned_module_helper)
    prepare_id = fact_id(table, "_prepare")

    assert result.fix is not None and class_owned_module_helper.query_fix_safety is not None
    rewrites = result.fix.rewrites.collect().filter(pl.col("fact_id") == prepare_id)
    nodes = result.fix.nodes.collect().filter(pl.col("fact_id") == prepare_id)
    assert (
        class_owned_module_helper.query_fix_safety.value,
        rewrites.get_column("kind").to_list(),
        rewrites.get_column("source").to_list(),
        nodes.get_column("role").to_list(),
    ) == (
        "review",
        ["move", "replace"],
        ["@staticmethod\n", "Cache._prepare(value)"],
        ["target", "anchor", "target"],
    )


def test_python_function_contracts_use_the_same_native_table(tmp_path: Path) -> None:
    table = function_table(tmp_path)
    assert value(table, unjustified_positional_only_parameter_count, "positional") == 1
    assert value(table, unjustified_positional_only_parameter_count, "read1") == 0
    assert value(table, task_group_candidate, "concurrent") == 1
    assert value(table, instance_independent_cached_property, "version") == 1
    assert value(table, cached_instance_method, "compute") == 1
    assert value(table, compact_house_docstring, "documented") == 0
    assert value(table, compact_house_docstring, "documented_directive") == 0
    assert value(table, compact_house_docstring, "undocumented") == 1
    assert value(table, tensor_docstring_semantics, "tensor") == 1


def test_every_function_rule_is_invoked_once_for_all_rows(tmp_path: Path) -> None:
    table = function_table(tmp_path)
    result = query(table, function_conditional_count)
    assert result.values.collect().height == table.frame(FunctionRelation.FUNCTIONS).height
