from typing import TYPE_CHECKING

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import SyntaxFact
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import (
    debug_artifact_left_behind,
    deeply_nested_body,
    statement_without_effect,
    superfluous_else_after_jump,
)
from mcmr.table import AnalysisSession, SyntaxRelation, Table

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def written(root: Path, sources: Mapping[str, str]) -> Path:
    """Write one native syntax-provider corpus."""
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


def table(root: Path) -> Table[SyntaxFact]:
    """Parse declarations into specialized syntax relations."""
    return AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[SyntaxFact.__name__],
    ).syntax_tables()


def query(
    rule: RuleContract,
    subject: Table[SyntaxFact],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one control rule exactly once over every declaration."""
    result = rule.invoke_table(
        subject,
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic control rule returned a model query")
    return result


def value(
    rule: RuleContract,
    subject: Table[SyntaxFact],
    qualname: str,
    **settings: RuleSetting,
) -> RuleValue:
    """Return one declaration's scalar after one repository-wide query."""
    facts = subject.frame(SyntaxRelation.FACTS).select("fact_id", "qualname")
    values = query(rule, subject, **settings).values.collect().join(facts, on="fact_id")
    return scalar_frame_value(values.filter(values["qualname"] == qualname))


def findings(rule: RuleContract, subject: Table[SyntaxFact]) -> list[dict[str, str | int]]:
    """Return ordered finding rows with exact source locations and messages."""
    held = query(rule, subject).findings
    if held is None:
        return []
    return held.rows.collect().select("message", "path", "start_line").to_dicts()


def core_repository(root: Path) -> Table[SyntaxFact]:
    """Build the shared control-flow corpus once per test."""
    return table(
        written(
            root,
            {
                "subject.py": """def jumped(values):
    if not values:
        return 0
    else:
        return 1


def kept(values):
    if not values:
        total = 0
    else:
        total = 1
    return total


def inert(order):
    order.total == 0
    order.items
    not order.paid
    charge(order)
    "Settle every order."
    local[head]
    remote["bash"] & foreground
    line += int(order.total == target)


def debug(order):
    print(order.card)
    breakpoint()


def logged(order):
    logger.debug(order)


def deep(items):
    for group in items:
        if group:
            for item in group:
                if item:
                    charge(item)


def shallow(items):
    for item in items:
        if item:
            charge(item)


def flat(value):
    return normalize(transform(value.member))
"""
            },
        )
    )


def test_an_else_is_reported_only_after_a_jump(tmp_path: Path) -> None:
    subject = core_repository(tmp_path)

    assert value(superfluous_else_after_jump, subject, "jumped") == 1
    assert value(superfluous_else_after_jump, subject, "kept") == 0
    assert value(superfluous_else_after_jump, subject, "jumped", jumps=["panic!"]) == 0
    assert findings(superfluous_else_after_jump, subject) == [
        {
            "message": "branch at `subject.py:2-5` keeps an alternative after its first arm jumps",
            "path": "subject.py",
            "start_line": 2,
        }
    ]


def test_only_whole_inert_statements_are_reported(tmp_path: Path) -> None:
    subject = core_repository(tmp_path)

    assert value(statement_without_effect, subject, "inert") == 3
    assert value(statement_without_effect, subject, "inert", inert_kinds=["literal"]) == 0
    assert value(statement_without_effect, subject, "logged") == 0
    assert value(statement_without_effect, subject, "flat") == 0
    assert [finding["start_line"] for finding in findings(statement_without_effect, subject)] == [
        17,
        18,
        19,
    ]
    assert [finding["message"] for finding in findings(statement_without_effect, subject)] == [
        "operation expression `order.total == 0` is discarded",
        "member expression `order.items` is discarded",
        "operation expression `not order.paid` is discarded",
    ]


def test_debug_artifacts_keep_exact_names_and_locations(tmp_path: Path) -> None:
    subject = core_repository(tmp_path)

    assert value(debug_artifact_left_behind, subject, "debug") == 2
    assert value(debug_artifact_left_behind, subject, "logged") == 0
    assert value(debug_artifact_left_behind, subject, "debug", artifacts=["dbg!"]) == 0
    assert findings(debug_artifact_left_behind, subject) == [
        {
            "message": "`print` leaves 1 debug artifact behind",
            "path": "subject.py",
            "start_line": 28,
        },
        {
            "message": "`breakpoint` leaves 1 debug artifact behind",
            "path": "subject.py",
            "start_line": 29,
        },
    ]


def test_test_and_cli_paths_are_exempt_but_bindings_are_not(tmp_path: Path) -> None:
    subject = table(
        written(
            tmp_path,
            {
                "tests/test_orders.py": "def render():\n    print('test')\n",
                "src/cli.py": "def render_cli():\n    print('cli')\n",
                "src/bindings.py": "def render_binding():\n    print('binding')\n",
            },
        )
    )

    assert value(debug_artifact_left_behind, subject, "render") == 0
    assert value(debug_artifact_left_behind, subject, "render_cli") == 0
    assert value(debug_artifact_left_behind, subject, "render_binding") == 1
    assert findings(debug_artifact_left_behind, subject) == [
        {
            "message": "`print` leaves 1 debug artifact behind",
            "path": "src/bindings.py",
            "start_line": 2,
        }
    ]


def test_only_body_constructs_count_toward_depth(tmp_path: Path) -> None:
    subject = core_repository(tmp_path)

    assert value(deeply_nested_body, subject, "deep") is True
    assert value(deeply_nested_body, subject, "deep", maximum_depth=5) is False
    assert value(deeply_nested_body, subject, "shallow") is False
    assert value(deeply_nested_body, subject, "shallow", maximum_depth=1) is True
    assert value(deeply_nested_body, subject, "flat") is False
    assert value(deeply_nested_body, subject, "deep", body_kinds=["loop"]) is False
    assert findings(deeply_nested_body, subject) == [
        {
            "message": "`deep` nests bodies 4 levels deep, past the ceiling of 3",
            "path": "subject.py",
            "start_line": 36,
        }
    ]


@pytest.mark.parametrize(
    "rule",
    (
        superfluous_else_after_jump,
        statement_without_effect,
        debug_artifact_left_behind,
        deeply_nested_body,
    ),
)
def test_an_empty_repository_produces_no_control_rows(tmp_path: Path, rule: RuleContract) -> None:
    subject = table(written(tmp_path, {"empty.py": ""}))

    assert query(rule, subject).values.collect().is_empty()
