import pytest

from mcmr.facts import (
    ArchitectureCharacteristic,
    ArchitectureCharacteristicFact,
    DependencyComponentFact,
    DependencyEdge,
    ModuleFact,
    ModuleMember,
    SourceSpan,
)
from mcmr.rules.general.deterministic.architecture.r0010 import (
    architecture_fitness_coverage,
)
from mcmr.rules.general.deterministic.architecture.r0011 import import_cycles
from mcmr.rules.general.llm.architecture.r2001 import module_cohesion

SPAN = SourceSpan(path="project")


def characteristic(**changes: bool | int | str) -> ArchitectureCharacteristic:
    """Build a fully protected architecture characteristic with selected changes."""
    values: dict[str, bool | int | str] = {
        "name": "latency",
        "has_objective": True,
        "has_executable_check": True,
        "has_retained_result": True,
        "has_owner": True,
        "has_scope": True,
        "observation_age_days": 1,
        "is_in_ci": True,
    }
    return ArchitectureCharacteristic.model_validate(values | changes)


@pytest.mark.parametrize(
    ("characteristics", "require_ci", "expected"),
    [
        ([], True, 0.0),
        ([characteristic()], True, 100.0),
        ([characteristic(is_in_ci=False)], True, 0.0),
        ([characteristic(is_in_ci=False)], False, 100.0),
        ([characteristic(observation_age_days=31)], True, 0.0),
        (
            [
                characteristic(),
                characteristic(name="security", has_retained_result=False),
            ],
            True,
            50.0,
        ),
        (
            [
                characteristic(
                    is_automatable=False,
                    is_in_ci=False,
                    has_repeatable_review=True,
                )
            ],
            True,
            100.0,
        ),
    ],
)
def test_architecture_fitness_cases(
    characteristics: list[ArchitectureCharacteristic],
    require_ci: bool,
    expected: float,
) -> None:
    fact = ArchitectureCharacteristicFact(
        key="architecture",
        span=SPAN,
        characteristics=characteristics,
    )
    assert architecture_fitness_coverage(fact, require_ci=require_ci) == expected


def edge(source: str, target: str, line: int = 1) -> DependencyEdge:
    """State one import between two modules, at the file and line the importer writes it on."""
    return DependencyEdge(source=source, target=target, path=f"{source}.py", line=line)


@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        ([], 0),
        ([edge("a", "a")], 1),
        ([edge("a", "b"), edge("b", "a")], 1),
        ([edge("a", "c"), edge("b", "c")], 0),
        ([edge("a", "b"), edge("b", "c"), edge("c", "a")], 1),
        ([edge("a", "b"), edge("b", "a"), edge("c", "d"), edge("d", "c")], 2),
        ([edge("a", "b"), edge("b", "a"), edge("c", "d")], 1),
    ],
)
def test_import_cycle_cases(edges: list[DependencyEdge], expected: int) -> None:
    fact = DependencyComponentFact(key="imports", span=SPAN, import_edges=edges)
    assert import_cycles(fact).value == expected


def test_an_import_cycle_names_its_modules_and_points_at_one_arrow_inside_it() -> None:
    """The count says how many tangles there are and the finding says which modules are in one."""
    fact = DependencyComponentFact(
        key="imports",
        span=SPAN,
        import_edges=[edge("pkg.a", "pkg.b", 4), edge("pkg.b", "pkg.a", 9), edge("pkg.a", "json")],
    )

    answer = import_cycles(fact)

    assert answer.value == 1
    assert answer.findings[0].message == (
        "2 modules import each other in one cycle, which are `pkg.a`, `pkg.b`, and `pkg.a` "
        "importing `pkg.b` is one of the 2 arrows closing it"
    )
    assert answer.findings[0].span.location == "pkg.a.py:4"
    assert [item.value for item in answer.findings[0].measurements] == [2.0, 2.0]
    assert answer.findings[0].repair is not None
    assert answer.findings[0].repair.summary.startswith("break the cycle holding `pkg.a`")


def test_two_separate_cycles_are_reported_one_finding_each() -> None:
    """A repository with two tangles has two decisions to make rather than one."""
    fact = DependencyComponentFact(
        key="imports",
        span=SPAN,
        import_edges=[edge("z.a", "z.b"), edge("z.b", "z.a"), edge("m.c", "m.c")],
    )

    answer = import_cycles(fact)

    assert answer.value == 2
    assert [finding.span.path for finding in answer.findings] == ["m.c.py", "z.a.py"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("members", "is_integration_boundary", "expected"),
    [
        ([], False, "uncertain"),
        ([ModuleMember(name="parse", responsibility="invoice")], False, "cohesive"),
        (
            [
                ModuleMember(name="parse", responsibility="invoice"),
                ModuleMember(name="send", responsibility="email"),
            ],
            False,
            "mixed",
        ),
        (
            [
                ModuleMember(name="wire_invoice", responsibility="invoice"),
                ModuleMember(name="wire_email", responsibility="email"),
            ],
            True,
            "intentional_integration",
        ),
    ],
)
async def test_module_cohesion_cases(
    members: list[ModuleMember],
    is_integration_boundary: bool,
    expected: str,
) -> None:
    fact = ModuleFact(
        key="module",
        span=SPAN,
        members=members,
        is_integration_boundary=is_integration_boundary,
    )
    assert await module_cohesion(fact) == expected
