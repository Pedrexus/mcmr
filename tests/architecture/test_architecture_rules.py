from enum import StrEnum
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.contextual.evaluation import ContextualSweep
from mcmr.domain.contracts import ModelProvenance, RuleContract, RuleSetting
from mcmr.execution import Classification, ClassificationBackend, ModelCandidate
from mcmr.execution.queries import ModelQuery
from mcmr.facts import (
    ArchitectureCharacteristic,
    ArchitectureCharacteristicFact,
    DependencyComponentFact,
    DependencyEdge,
    ModuleFact,
    SourceSpan,
)
from mcmr.plugins import Fact, Table
from mcmr.plugins import fact_table as in_memory_table
from mcmr.query import RuleQuery
from mcmr.rules.general import (
    ModuleCohesion,
    architecture_fitness_coverage,
    import_cycles,
    module_cohesion,
)

if TYPE_CHECKING:
    from pathlib import Path

_SPAN = SourceSpan(path="project")


def characteristic(**changes: int | str | None) -> ArchitectureCharacteristic:
    """Build a fully protected architecture characteristic with selected changes."""
    values: dict[str, int | str | None] = {
        "name": "latency",
        "objective": "p99 below 200 milliseconds",
        "check": "chefe run benchmark",
        "retained_result": "passed",
        "owner": "performance",
        "scope": "checkout API",
        "observation_age_days": 1,
        "verification": "ci",
    }
    return ArchitectureCharacteristic.model_validate(values | changes)


def fact_table[Family: Fact](
    fact: Family,
    root: Path,
) -> Table[Family]:
    """Normalize one controlled fact through the in-memory Rust transport."""
    return in_memory_table(type(fact), [fact])


def queried[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one deterministic rule once over its complete table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic architecture rule returned a model query")
    return result


@pytest.mark.parametrize(
    ("characteristics", "require_ci", "expected"),
    [
        ([], True, 0.0),
        ([characteristic()], True, 100.0),
        ([characteristic(verification="manual")], True, 0.0),
        ([characteristic(verification="manual")], False, 100.0),
        ([characteristic(observation_age_days=31)], True, 0.0),
        (
            [
                characteristic(),
                characteristic(name="security", retained_result=""),
            ],
            True,
            50.0,
        ),
        (
            [characteristic(verification="repeatable_review")],
            True,
            100.0,
        ),
    ],
)
def test_architecture_fitness_cases(
    characteristics: list[ArchitectureCharacteristic],
    *,
    require_ci: bool,
    expected: float,
    tmp_path: Path,
) -> None:
    fact = ArchitectureCharacteristicFact(
        key="architecture",
        span=_SPAN,
        characteristics=characteristics,
    )
    query = queried(
        architecture_fitness_coverage,
        fact_table(fact, tmp_path),
        require_ci=require_ci,
    )
    assert query.values.collect().item(0, "float_value") == expected


def edge(
    source: str,
    *,
    target: str,
    line: int = 1,
    source_component: int = 0,
    target_component: int = 0,
) -> DependencyEdge:
    """State one import between two modules, at the file and line the importer writes it on."""
    return DependencyEdge(
        source=source,
        target=target,
        path=f"{source}.py",
        line=line,
        source_component=source_component,
        target_component=target_component,
    )


@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        ([], 0),
        ([edge("a", target="a")], 1),
        ([edge("a", target="b"), edge("b", target="a")], 1),
        (
            [
                edge("a", target="c", source_component=0, target_component=2),
                edge("b", target="c", source_component=1, target_component=2),
            ],
            0,
        ),
        ([edge("a", target="b"), edge("b", target="c"), edge("c", target="a")], 1),
        (
            [
                edge("a", target="b"),
                edge("b", target="a"),
                edge("c", target="d", source_component=1, target_component=1),
                edge("d", target="c", source_component=1, target_component=1),
            ],
            2,
        ),
        (
            [
                edge("a", target="b"),
                edge("b", target="a"),
                edge("c", target="d", source_component=1, target_component=2),
            ],
            1,
        ),
    ],
)
def test_import_cycle_cases(edges: list[DependencyEdge], expected: int, tmp_path: Path) -> None:
    fact = DependencyComponentFact(key="imports", span=_SPAN, import_edges=edges)
    query = queried(import_cycles, fact_table(fact, tmp_path))
    assert query.values.collect().item(0, "integer_value") == expected


def test_an_import_cycle_names_its_modules_and_points_at_one_arrow_inside_it(
    tmp_path: Path,
) -> None:
    """The count says how many tangles there are and the finding says which modules are in one."""
    fact = DependencyComponentFact(
        key="imports",
        span=_SPAN,
        import_edges=[
            edge("pkg.a", target="pkg.b", line=4),
            edge("pkg.b", target="pkg.a", line=9),
            edge("pkg.a", target="json", source_component=0, target_component=1),
        ],
    )

    answer = queried(import_cycles, fact_table(fact, tmp_path))
    values = answer.values.collect()
    assert answer.findings is not None
    findings = answer.findings.rows.collect()

    assert (
        values.item(0, "integer_value"),
        findings.item(0, "message"),
        findings.item(0, "path"),
        findings.item(0, "start_line"),
        findings.get_column("measurement_values").to_list()[0],
    ) == (
        1,
        "2 modules import each other in one cycle, which are `pkg.a`, `pkg.b`, and `pkg.a` "
        "importing `pkg.b` is one of the 2 arrows closing it",
        "pkg.a.py",
        4,
        [2.0, 2.0],
    )
    assert findings.item(0, "choice_question").startswith("break the cycle holding `pkg.a`")


def test_two_separate_cycles_are_reported_one_finding_each(tmp_path: Path) -> None:
    """A repository with two tangles has two decisions to make rather than one."""
    fact = DependencyComponentFact(
        key="imports",
        span=_SPAN,
        import_edges=[
            edge("z.a", target="z.b"),
            edge("z.b", target="z.a"),
            edge("m.c", target="m.c", source_component=1, target_component=1),
        ],
    )

    answer = queried(import_cycles, fact_table(fact, tmp_path))
    values = answer.values.collect()
    assert answer.findings is not None
    findings = answer.findings.rows.collect()

    assert values.item(0, "integer_value") == 2
    assert set(findings.get_column("path")) == {"m.c.py", "z.a.py"}


class FixedCohesion(ClassificationBackend):
    """Return one selected cohesion judgment while checking the closed rubric."""

    answer: ModuleCohesion

    async def classify_candidate[Category: StrEnum](
        self, candidate: ModelCandidate, *, category: type[Category], instructions: str
    ) -> Classification[Category]:
        """Return the selected category after verifying that evidence and instructions arrived."""
        assert candidate.fact_id
        assert instructions
        return Classification(
            value=category(self.answer),
            reasoning="Controlled cohesion classification.",
            evidence=list(candidate.retained),
            confidence=1.0,
            provenance=ModelProvenance(
                backend="controlled",
                model="test",
                reasoning_effort="none",
            ),
        )


@pytest.mark.anyio
@pytest.mark.parametrize("expected", list(ModuleCohesion))
async def test_module_cohesion_uses_the_judgment_backend(expected: ModuleCohesion) -> None:
    backend = FixedCohesion(answer=expected)
    query = module_cohesion.invoke_table(
        cast(
            "Table[Fact]",
            cast("Table[ModuleFact]", ContextualSweep.table(ModuleFact, "ALL-ARCH1001")),
        ),
        settings={},
        dependencies={ClassificationBackend: backend},
    )
    if not isinstance(query, ModelQuery):
        raise TypeError("a contextual architecture rule returned a deterministic query")
    resolved = await backend.resolve(query)
    assert resolved.values.collect().item(0, "category_value") == expected
