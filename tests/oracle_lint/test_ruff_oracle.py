from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings

from mcmr.facts import SyntaxFact

from ..oracle import (
    DeclarationReader,
    Oracle,
    Relation,
    Report,
    Shape,
    Site,
    Source,
    Trees,
    assembled,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [needs_kernel, needs("ruff")]


@pytest.fixture(scope="module")
def trees(tmp_path_factory: pytest.TempPathFactory) -> Trees:
    """Hand every drawn example a tree of its own, since a reading is cached by the tree."""
    return Trees(root=tmp_path_factory.mktemp("branch"))


# Ruff splits this question across several codes. The oracle therefore compares their union rather
# than whichever code one generated example happens to produce.
_RETURNING = ("RET505", "RET506", "RET507", "RET508")


def jumping(name: str, *, jump: str, alternatives: int) -> Shape:
    """Return one callable leaving a branch through a jump, with alternatives behind it.

    Ruff reports one diagnostic for a whole chain and points it at the first clause the jump made
    unnecessary, which is the opening `elif` where the chain has one and the `else` where it has
    none. The shape states that line itself, so the property has an opinion of its own rather than
    only comparing two readers of the same text.
    """
    lines = [f"def {name}(value):", "    if value:", f"        {jump}"]
    for index in range(alternatives):
        lines += [f"    elif value == {index}:", f"        {jump}"]
    lines += ["    else:", "        return 1"]
    return Shape(body=lines, reported={3 if alternatives else len(lines) - 2})


_JUMPING: list[Shape] = [
    jumping(f"m{index}", jump=jump, alternatives=alternatives)
    for index, (jump, alternatives) in enumerate(
        (jump, alternatives)
        for jump in ("return None", "raise ValueError('no')")
        for alternatives in range(3)
    )
]


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(assembled(_JUMPING))
def test_superfluous_else_agrees_with_ruff(trees: Trees, source: Source) -> None:
    """MCMR generalizes RET505 through RET508, so on Python it owes Ruff's own answer.

    Two comparisons rather than one. The strategy says which line each chain made unnecessary and
    is held to Ruff for it, which is what keeps the generator honest, and MCMR is then held to the
    same four codes. A rule reading a declaration answers for the whole of it, so Ruff's lines are
    folded into the callables MCMR reported and a finding in the wrong callable fails even when the
    totals agree.
    """
    root = trees.grow({"generated.py": source.text})
    oracle = [Oracle.of("ruff", code).report(root) for code in _RETURNING]
    stated = Report(
        reader="the strategy",
        sites=[Site.at("generated.py", line) for line in source.reported],
    )

    differ(
        stated,
        Relation.UNION,
        *oracle,
        because="every shape drawn here states the clause its own jump made unnecessary",
    )
    differ(
        DeclarationReader(rule_id="ALL-CONT0001", family=SyntaxFact).report(root),
        Relation.UNION,
        *oracle,
        because="Ruff answers this by the kind of jump and MCMR answers it once for the branch",
    )


def test_statement_without_effect_is_what_two_ruff_rules_report_together(tmp_path: Path) -> None:
    """B015 and B018 between them report exactly what this rule generalizes."""
    root = written(
        tmp_path,
        {
            "generated.py": """def run(order, values):
    order.total
    values == 3
    total = order.total
    return total
"""
        },
    )
    comparison = Oracle.of("ruff", "B015").report(root)
    expression = Oracle.of("ruff", "B018").report(root)

    assert comparison.states(Site.at("generated.py", 3))
    assert expression.states(Site.at("generated.py", 2))
    differ(
        DeclarationReader(rule_id="ALL-CONT0002", family=SyntaxFact).report(root),
        Relation.UNION,
        comparison,
        expression,
        because="Ruff splits a discarded value into a comparison and an expression, MCMR does not",
    )


def test_debug_artifact_agrees_with_ruff(tmp_path: Path) -> None:
    """T201 reports the print this rule reports, and ignores the logger call it ignores."""
    root = written(
        tmp_path,
        {
            "generated.py": """import logging

logger = logging.getLogger(__name__)


def run(value):
    print(value)
    logger.info(value)
    return value
"""
        },
    )
    oracle = Oracle.of("ruff", "T201").report(root)

    assert oracle.states(Site.at("generated.py", 7))
    differ(
        DeclarationReader(rule_id="ALL-CONT0003", family=SyntaxFact).report(root),
        Relation.EQUALS,
        oracle,
        because="a console print is the same artifact to both readers",
    )


def test_swallowed_error_covers_everything_ruff_reports_and_more(tmp_path: Path) -> None:
    """MCMR is deliberately wider than S110 here, and the extra finding is written out in full.

    Ruff reports a discarded failure only where the handler catches broadly. Swallowing a named
    failure silently is the same defect with a narrower blast radius, so MCMR reports both. Saying
    that as Ruff's answer plus the line Ruff would have named keeps the comparison an equality,
    where a containment would have been satisfied by MCMR reporting nothing at all.
    """
    catching = "def run(value):\n    try:\n        return int(value)\n    except {}:\n        {}\n"
    blind = written(tmp_path / "blind", {"generated.py": catching.format("Exception", "pass")})
    named = written(tmp_path / "named", {"generated.py": catching.format("ValueError", "pass")})
    handled = written(
        tmp_path / "handled", {"generated.py": catching.format("ValueError", "return 0")}
    )
    rule = DeclarationReader(rule_id="ALL-ERRO0001", family=SyntaxFact)

    broadly, narrowly, kept = (
        Oracle.of("ruff", "S110").report(root) for root in (blind, named, handled)
    )
    assert broadly.states(Site.at("generated.py", 4)) and narrowly.states() and kept.states()
    comparisons = [
        (
            blind,
            broadly,
            "a blind catch discarding its failure is the same defect to both readers",
        ),
        (
            named,
            narrowly.plus(Site.at("generated.py", 4)),
            "S110 asks for a broad catch where MCMR asks only that the failure was discarded",
        ),
        (
            handled,
            kept,
            "a handler that does something is not a swallowed failure to either reader",
        ),
    ]
    for root, expected, because in comparisons:
        differ(rule.report(root), Relation.EQUALS, expected, because=because)


def test_raise_without_cause_agrees_with_ruff(tmp_path: Path) -> None:
    """B904 reports the raise that drops the failure it replaces."""
    root = written(
        tmp_path,
        {
            "generated.py": """def run(value):
    try:
        return int(value)
    except ValueError:
        raise RuntimeError('bad')


def kept(value):
    try:
        return int(value)
    except ValueError as failure:
        raise RuntimeError('bad') from failure
"""
        },
    )
    oracle = Oracle.of("ruff", "B904").report(root)

    assert oracle.states(Site.at("generated.py", 5))
    differ(
        DeclarationReader(rule_id="ALL-ERRO0002", family=SyntaxFact).report(root),
        Relation.EQUALS,
        oracle,
        because="a raise that drops the failure it replaces is the same defect to both readers",
    )
