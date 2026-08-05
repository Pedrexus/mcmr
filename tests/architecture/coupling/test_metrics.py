from collections.abc import Sequence

import polars as pl
from hypothesis import given
from hypothesis import strategies as st

from mcmr.rules.general import (
    PackageCoupling,
    abstraction_nothing_depends_on,
    dependency_on_a_less_stable_module,
)

from .support import count_value, count_values, coupling, fact, fact_table, query, value


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


def test_test_code_may_depend_on_volatile_production_code() -> None:
    """A verification dependency is not a production component layering decision."""
    subject = fact(
        module="tests.shared.case",
        path="tests/shared/case.py",
        dependencies=[coupling("pkg.cli.command", afferent=0, efferent=0)],
    )
    callers = [
        fact(
            module=f"tests.caller{index}.case",
            path=f"tests/caller{index}/case.py",
            dependencies=[coupling("tests.shared.case", afferent=0, efferent=0)],
        )
        for index in range(3)
    ]
    volatile = fact(
        module="pkg.cli.command",
        path="src/pkg/cli/command.py",
        dependencies=[coupling("pkg.output.sink", afferent=0, efferent=0)],
    )

    result = query(
        fact_table(
            subject,
            *callers,
            volatile,
            fact(module="pkg.output.sink", path="src/pkg/output/sink.py"),
        ),
        dependency_on_a_less_stable_module,
    )

    assert not any(count_values(result))


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
