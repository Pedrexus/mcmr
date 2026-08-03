from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import Fact, ModuleCoupling, ModuleCouplingFact, SourceSpan
from mcmr.kernel import Kernel
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import (
    PackageCoupling,
    abstraction_nothing_depends_on,
    dependency_on_a_less_stable_module,
)
from mcmr.table import Table
from mcmr.table import fact_table as in_memory_table

from ..support import kernel_binary, needs_kernel


def test_package_name_without_a_path_uses_the_enclosing_module() -> None:
    frame = pl.DataFrame({"module": ["pkg.service.operation"]})

    assert frame.select(PackageCoupling.package("module").alias("package")).item() == (
        "pkg.service"
    )


def test_language_package_modules_keep_the_package_they_declare() -> None:
    frame = pl.DataFrame(
        {
            "module": ["pkg.api", "core.bindings", "pkg.service.operation"],
            "path": ["pkg/api/__init__.py", "src/bindings/mod.rs", "pkg/service/operation.py"],
        }
    )

    packages = frame.select(
        PackageCoupling.package("module", path="path").alias("package")
    ).to_series()
    assert packages.to_list() == [
        "pkg.api",
        "core.bindings",
        "pkg.service",
    ]


def fact_table[Family: Fact](first: Family, *rest: Family) -> Table[Fact]:
    """Normalize one or more facts through a single in-memory native table."""
    subjects = (first, *rest)
    return in_memory_table(type(first), subjects)


def query(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one deterministic rule once over a retained table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic coupling rule returned a model query")
    return result


def values(result: RuleQuery) -> list[RuleValue]:
    """Return every scalar emitted by one table query in fact order."""
    return [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)]


def value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the one scalar emitted for a single retained fact."""
    answers = values(query(subject, rule, **settings))
    if len(answers) != 1:
        raise ValueError(f"expected one coupling value and received {len(answers)}")
    return answers[0]


def count_value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> int:
    """Return one integer scalar while refusing Boolean and non-count outputs."""
    answer = value(subject, rule, **settings)
    if isinstance(answer, bool) or not isinstance(answer, int):
        raise TypeError("the coupling rule did not emit an integer count")
    return answer


def count_values(result: RuleQuery) -> list[int]:
    """Return all integer scalars while refusing Boolean and non-count outputs."""
    answers = values(result)
    if any(isinstance(answer, bool) or not isinstance(answer, int) for answer in answers):
        raise TypeError("the coupling rule did not emit integer counts")
    return cast("list[int]", answers)


def coupling(module: str, *, afferent: int, efferent: int) -> ModuleCoupling:
    """Build the coupling of one module a rule reads through a dependency."""
    return ModuleCoupling(module=module, afferent_count=afferent, efferent_count=efferent)


def fact(
    *,
    module: str = "pkg.subject",
    path: str | None = None,
    afferent: int = 0,
    efferent: int = 0,
    types: int = 0,
    abstract: int = 0,
    dependencies: list[ModuleCoupling] | None = None,
) -> ModuleCouplingFact:
    """Build one module's coupling fact from the four counts the kernel states."""
    return ModuleCouplingFact(
        key=f"coupling:{module}",
        span=SourceSpan(path=path or f"{module.replace('.', '/')}.py"),
        module=module,
        afferent_count=afferent,
        efferent_count=efferent,
        declaration_count=types,
        abstract_declaration_count=abstract,
        dependencies=[] if dependencies is None else dependencies,
    )


def test_instability_is_the_share_of_the_coupling_that_points_outward() -> None:
    """Every value here is `Ce / (Ca + Ce)` worked out by hand rather than by the model."""
    assert fact(afferent=2, efferent=0).instability == 0.0
    assert fact(afferent=1, efferent=1).instability == 0.5
    assert fact(afferent=0, efferent=2).instability == 1.0
    assert fact(afferent=3, efferent=1).instability == 0.25
    assert fact(afferent=1, efferent=3).instability == 0.75


def test_a_module_no_arrow_touches_has_no_ratio_to_state_and_reads_as_stable() -> None:
    """Zero over zero is the one case the formula cannot answer, so the convention answers it."""
    assert fact().instability == 0.0
    assert coupling("pkg.alone", afferent=0, efferent=0).instability == 0.0


def test_abstractness_is_the_share_of_declared_types_that_state_a_contract() -> None:
    """Four exact ratios, and the empty module that has no types to take a share of."""
    assert fact(types=4, abstract=1).abstractness == 0.25
    assert fact(types=2, abstract=1).abstractness == 0.5
    assert fact(types=3, abstract=3).abstractness == 1.0
    assert fact(types=5, abstract=0).abstractness == 0.0
    assert fact(types=0, abstract=0).abstractness == 0.0


def test_distance_is_how_far_the_module_sits_from_the_line_a_plus_i_equals_one() -> None:
    """`D = |A + I - 1|`, computed here from the `A` and `I` the two tests above pinned."""
    assert fact(afferent=2, efferent=0, types=4, abstract=1).distance == 0.75
    assert fact(afferent=1, efferent=1, types=2, abstract=1).distance == 0.0
    assert fact(afferent=0, efferent=2, types=0).distance == 0.0
    assert fact(afferent=3, efferent=0, types=1, abstract=1).distance == 0.0
    assert fact(afferent=3, efferent=0, types=1, abstract=0).distance == 1.0
    assert fact(afferent=0, efferent=3, types=1, abstract=1).distance == 1.0


@given(
    afferent=st.integers(min_value=0, max_value=500),
    efferent=st.integers(min_value=0, max_value=500),
    types=st.integers(min_value=0, max_value=200),
)
def test_every_module_lands_inside_the_unit_square_whatever_its_counts(
    *, afferent: int, efferent: int, types: int
) -> None:
    """`A`, `I`, and `D` are shares, so no arrangement of counts can push one outside its range.

    The zero counts are inside the range on purpose, since a module nothing imports and that
    imports nothing is the case that divides by zero if the convention is missing.
    """
    subject = fact(afferent=afferent, efferent=efferent, types=types, abstract=types // 2)

    assert 0.0 <= subject.instability <= 1.0
    assert 0.0 <= subject.abstractness <= 1.0
    assert 0.0 <= subject.distance <= 1.0
    assert subject.distance == abs(subject.abstractness + subject.instability - 1.0)


@given(
    afferent=st.integers(min_value=0, max_value=200),
    efferent=st.integers(min_value=1, max_value=200),
)
def test_taking_on_one_more_dependent_never_makes_a_module_less_stable(
    *, afferent: int, efferent: int
) -> None:
    """Instability falls as dependents arrive, which is the whole reason it is called that."""
    before = fact(afferent=afferent, efferent=efferent).instability
    after = fact(afferent=afferent + 1, efferent=efferent).instability

    assert after < before


@given(types=st.integers(min_value=1, max_value=100), share=st.floats(0.0, 1.0))
def test_abstractness_is_exactly_the_fraction_the_counts_state(types: int, share: float) -> None:
    """A ratio of two counts has one right answer, so this asserts equality rather than a band."""
    abstract = round(types * share)
    subject = fact(types=types, abstract=abstract)

    assert subject.abstractness == abstract / types


def test_an_arrow_toward_something_less_stable_is_the_one_this_rule_counts() -> None:
    """One package at `I = 0.5` points to exactly one package above it."""
    subject = fact(
        module="subject.core",
        dependencies=[
            coupling("settled.api", afferent=0, efferent=0),
            coupling("matched.api", afferent=0, efferent=0),
            coupling("volatile.api", afferent=0, efferent=0),
        ],
    )
    callers = [
        fact(
            module=f"caller{index}.api",
            dependencies=[coupling("subject.core", afferent=0, efferent=0)],
        )
        for index in range(3)
    ]
    matched = fact(
        module="matched.core",
        dependencies=[coupling("settled.api", afferent=0, efferent=0)],
    )
    volatile = fact(
        module="volatile.core",
        dependencies=[
            coupling("output1.api", afferent=0, efferent=0),
            coupling("output2.api", afferent=0, efferent=0),
        ],
    )

    result = query(
        fact_table(
            fact(module="subject", path="subject/__init__.py"),
            subject,
            *callers,
            matched,
            volatile,
            fact(module="settled.api"),
            fact(module="matched.api"),
            fact(module="volatile.api"),
            fact(module="output1.api"),
            fact(module="output2.api"),
        ),
        dependency_on_a_less_stable_module,
    )

    assert sum(count_values(result)) == 1
    assert result.findings is not None
    assert result.findings.rows.collect().item(0, "path") == "subject/core.py"


def test_tolerance_is_the_slack_a_project_allows_before_a_difference_counts() -> None:
    """Two packages a hair apart are no layering problem when the setting allows the gap."""
    subject = fact(
        module="subject.core",
        dependencies=[coupling("near.api", afferent=0, efferent=0)],
    )
    facts = [
        subject,
        *(
            fact(
                module=f"caller{index}.api",
                dependencies=[coupling("subject.core", afferent=0, efferent=0)],
            )
            for index in range(3)
        ),
        fact(
            module="near.core",
            dependencies=[coupling("sink.api", afferent=0, efferent=0)],
        ),
        fact(
            module="nearcaller.api",
            dependencies=[coupling("near.core", afferent=0, efferent=0)],
        ),
        fact(module="near.api"),
        fact(module="sink.api"),
    ]

    table = fact_table(facts[0], *facts[1:])
    assert sum(count_values(query(table, dependency_on_a_less_stable_module))) == 1
    assert sum(count_values(query(table, dependency_on_a_less_stable_module, tolerance=0.1))) == 0


def test_a_module_importing_nothing_internal_can_never_violate_the_principle() -> None:
    """With no arrow leaving it there is nothing to point the wrong way."""
    assert (
        value(
            fact_table(fact(afferent=9)),
            dependency_on_a_less_stable_module,
        )
        == 0
    )


@given(
    afferent=st.integers(min_value=0, max_value=50),
    dependents=st.lists(
        st.tuples(st.integers(min_value=0, max_value=50), st.integers(min_value=1, max_value=50)),
        max_size=8,
    ),
)
def test_the_violation_count_never_exceeds_the_arrows_that_could_carry_one(
    afferent: int, dependents: Sequence[tuple[int, int]]
) -> None:
    """A count of a subset of the dependencies is bounded by how many dependencies there are."""
    subject = fact(
        afferent=afferent,
        efferent=len(dependents),
        dependencies=[
            coupling(f"pkg.other{index}", afferent=incoming, efferent=outgoing)
            for index, (incoming, outgoing) in enumerate(dependents)
        ],
    )

    assert (
        0
        <= count_value(fact_table(subject), dependency_on_a_less_stable_module)
        <= len(dependents)
    )


def test_an_abstraction_nothing_imports_is_scaffolding_and_one_with_callers_is_not() -> None:
    """Both halves are required, and each one alone leaves the module alone."""
    unused = fact(afferent=0, efferent=1, types=2, abstract=2)
    implemented = fact(afferent=6, efferent=1, types=2, abstract=2)
    concrete = fact(afferent=0, efferent=1, types=2)

    assert value(fact_table(unused), abstraction_nothing_depends_on) is True
    assert value(fact_table(implemented), abstraction_nothing_depends_on) is False
    assert value(fact_table(concrete), abstraction_nothing_depends_on) is False


def test_a_half_abstract_module_is_judged_against_the_share_the_project_states() -> None:
    """One contract among four types is scaffolding only where the project says it is."""
    subject = fact(afferent=0, efferent=1, types=4, abstract=1)

    assert subject.abstractness == 0.25
    table = fact_table(subject)
    assert value(table, abstraction_nothing_depends_on) is False
    assert value(table, abstraction_nothing_depends_on, minimum_abstractness=0.25) is True


def test_a_module_of_plain_functions_that_nothing_imports_is_left_alone() -> None:
    """A leaf with no types has an abstractness of zero, which is never a missing implementer."""
    assert (
        value(
            fact_table(fact(efferent=2)),
            abstraction_nothing_depends_on,
        )
        is False
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Write one package whose coupling and abstractness are small enough to work out by hand.

    `core` is imported by both other modules and imports neither, `reader` imports `core` and is
    imported by `writer`, and `writer` imports both and is imported by nothing. `core` declares
    four types of which one is a contract, `reader` declares two concrete ones, and `writer`
    declares none.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text(
        """from abc import ABC, abstractmethod


class Codec(ABC):
    @abstractmethod
    def encode(self) -> str: ...


class Frame:
    width = 1


class Packet:
    size = 2


class Header:
    kind = 3
"""
    )
    (package / "reader.py").write_text(
        """from pkg.core import Frame


class Reader:
    frame = Frame


class Buffer:
    depth = 4
"""
    )
    (package / "writer.py").write_text(
        """from pkg.core import Packet
from pkg.reader import Reader


def write(reader: Reader) -> Packet:
    return Packet()
"""
    )
    return tmp_path


@cache
def built(root: str) -> list[ModuleCouplingFact]:
    """Return the coupling facts this kernel builds for one repository root."""
    workspace = Kernel(binary=kernel_binary(), root=Path(root)).build(
        ["ModuleCouplingFact"], {"ModuleCouplingFact": ModuleCouplingFact}
    )
    return list(workspace.stream(ModuleCouplingFact))


def named(facts: Sequence[ModuleCouplingFact], module: str) -> ModuleCouplingFact:
    """Return one module's fact out of a stream, by the name the graph gave it."""
    return next(item for item in facts if item.module == module)


@needs_kernel
def test_the_kernel_states_the_counts_this_fixture_was_written_to_produce(
    repository: Path,
) -> None:
    """Every number below is read off the fixture rather than off the implementation."""
    facts = built(str(repository))
    core = named(facts, "pkg.core")
    reader = named(facts, "pkg.reader")
    writer = named(facts, "pkg.writer")

    assert [
        (
            fact.afferent_count,
            fact.efferent_count,
            fact.declaration_count,
            fact.abstract_declaration_count,
        )
        for fact in (core, reader, writer)
    ] == [(2, 0, 4, 1), (1, 1, 2, 0), (0, 2, 0, 0)]
    assert [item.module for item in writer.dependencies] == ["pkg.core", "pkg.reader"]
    assert writer.dependencies[0].afferent_count == 2


@needs_kernel
def test_the_metrics_over_that_fixture_are_the_ones_martin_defines(repository: Path) -> None:
    """`I`, `A`, and `D` for three modules, each worked out by hand from the counts above."""
    facts = built(str(repository))
    core = named(facts, "pkg.core")
    reader = named(facts, "pkg.reader")
    writer = named(facts, "pkg.writer")

    assert (core.instability, core.abstractness, core.distance) == (0.0, 0.25, 0.75)
    assert (reader.instability, reader.abstractness, reader.distance) == (0.5, 0.0, 0.5)
    assert (writer.instability, writer.abstractness, writer.distance) == (1.0, 0.0, 0.0)


@needs_kernel
def test_the_rules_read_that_fixture_the_way_the_metrics_say_they_should(
    repository: Path,
) -> None:
    """Every arrow points toward stability here, so the layering rule reports nothing at all."""
    facts = built(str(repository))
    table = fact_table(facts[0], *facts[1:])

    assert values(query(table, dependency_on_a_less_stable_module)) == [0]
    assert not any(values(query(table, abstraction_nothing_depends_on)))


@pytest.fixture
def inverted(tmp_path: Path) -> Path:
    """Write the same three modules with one arrow turned around, which is the violation.

    `core` now imports `writer`, and `writer` is imported by nothing else and imports two modules,
    so the settled module has taken a dependency on the volatile one.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text("from pkg.writer import write\n\n\nvalue = write\n")
    (package / "reader.py").write_text("from pkg.core import value\n\n\nread = value\n")
    (package / "writer.py").write_text(
        "from pkg.helper import helper\n\n\ndef write() -> int:\n    return helper()\n"
    )
    (package / "helper.py").write_text("def helper() -> int:\n    return 1\n")
    return tmp_path


@needs_kernel
def test_an_arrow_within_one_package_is_not_a_component_violation(
    inverted: Path,
) -> None:
    """A file edge inside one package never crosses the component boundary."""
    facts = built(str(inverted))
    core = named(facts, "pkg.core")
    writer = named(facts, "pkg.writer")

    assert (core.afferent_count, core.efferent_count) == (1, 1)
    assert (writer.afferent_count, writer.efferent_count) == (1, 1)
    assert core.instability == 0.5
    assert writer.instability == 0.5
    table = fact_table(core)
    assert value(table, dependency_on_a_less_stable_module) == 0
    assert value(table, dependency_on_a_less_stable_module, tolerance=-0.1) == 0


def test_a_package_initializer_declares_ownership_without_creating_a_component_arrow() -> None:
    """A public facade may reexport a nested implementation without depending on its volatility."""
    initializer = fact(
        module="pkg.api",
        path="pkg/api/__init__.py",
        dependencies=[coupling("pkg.api.models.item", afferent=0, efferent=0)],
    )
    model = fact(module="pkg.api.models.item", path="pkg/api/models/item.py")

    assert not any(
        values(
            query(
                fact_table(initializer, model),
                dependency_on_a_less_stable_module,
                tolerance=-0.1,
            )
        )
    )

    rust_facade = fact(
        module="engine.api",
        path="engine/src/api/mod.rs",
        dependencies=[coupling("engine.api.models.item", afferent=0, efferent=0)],
    )
    rust_model = fact(module="engine.api.models.item", path="engine/src/api/models/item.rs")
    assert not any(
        values(
            query(
                fact_table(rust_facade, rust_model),
                dependency_on_a_less_stable_module,
                tolerance=-0.1,
            )
        )
    )
