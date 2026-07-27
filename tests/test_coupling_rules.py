import json
import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr.facts import ModuleCoupling, ModuleCouplingFact, SourceSpan
from mcmr.kernel import Kernel
from mcmr.rules.general.deterministic.architecture.r0012 import (
    dependency_on_a_less_stable_module,
)
from mcmr.rules.general.deterministic.architecture.r0013 import (
    concrete_module_the_repository_leans_on,
)
from mcmr.rules.general.deterministic.architecture.r0014 import abstraction_nothing_depends_on
from tests.conftest import BINARY, ROOT, needs_kernel

ARCHY = Path(__file__).parents[2] / "archy"
SOURCE = ROOT / "src"

needs_archy = pytest.mark.skipif(
    not (ARCHY / "pyproject.toml").exists() or shutil.which("uv") is None,
    reason="the Stable Dependencies oracle needs the Archy checkout and uv",
)


def coupling(module: str, afferent: int, efferent: int) -> ModuleCoupling:
    """Build the coupling of one module a rule reads through a dependency."""
    return ModuleCoupling(module=module, afferent_count=afferent, efferent_count=efferent)


def fact(
    *,
    afferent: int = 0,
    efferent: int = 0,
    types: int = 0,
    abstract: int = 0,
    dependencies: tuple[ModuleCoupling, ...] = (),
) -> ModuleCouplingFact:
    """Build one module's coupling fact from the four counts the kernel states."""
    return ModuleCouplingFact(
        key="coupling:pkg.subject",
        span=SourceSpan(path="pkg/subject.py"),
        module="pkg.subject",
        afferent_count=afferent,
        efferent_count=efferent,
        declaration_count=types,
        abstract_declaration_count=abstract,
        dependencies=list(dependencies),
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
    assert coupling("pkg.alone", 0, 0).instability == 0.0


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
    afferent: int, efferent: int, types: int
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
    afferent: int, efferent: int
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
    """The subject is at `I = 0.5`, so only the dependency above it is reported."""
    subject = fact(
        afferent=1,
        efferent=3,
        dependencies=(
            coupling("pkg.settled", 4, 0),
            coupling("pkg.matched", 1, 1),
            coupling("pkg.volatile", 0, 2),
        ),
    )

    assert subject.instability == 0.75
    assert dependency_on_a_less_stable_module(subject).value == 1


def test_tolerance_is_the_slack_a_project_allows_before_a_difference_counts() -> None:
    """Two modules a hair apart are no layering problem, and the setting says how wide that is."""
    subject = fact(afferent=3, efferent=1, dependencies=(coupling("pkg.near", 2, 1),))

    assert subject.instability == 0.25
    assert coupling("pkg.near", 2, 1).instability == pytest.approx(1 / 3)
    assert dependency_on_a_less_stable_module(subject).value == 1
    assert dependency_on_a_less_stable_module(subject, tolerance=0.1).value == 0


def test_a_module_importing_nothing_internal_can_never_violate_the_principle() -> None:
    """With no arrow leaving it there is nothing to point the wrong way."""
    assert dependency_on_a_less_stable_module(fact(afferent=9)).value == 0


@given(
    afferent=st.integers(min_value=0, max_value=50),
    dependents=st.lists(
        st.tuples(st.integers(min_value=0, max_value=50), st.integers(min_value=1, max_value=50)),
        max_size=8,
    ),
)
def test_the_violation_count_never_exceeds_the_arrows_that_could_carry_one(
    afferent: int, dependents: list[tuple[int, int]]
) -> None:
    """A count of a subset of the dependencies is bounded by how many dependencies there are."""
    subject = fact(
        afferent=afferent,
        efferent=len(dependents),
        dependencies=tuple(
            coupling(f"pkg.other{index}", incoming, outgoing)
            for index, (incoming, outgoing) in enumerate(dependents)
        ),
    )

    assert 0 <= dependency_on_a_less_stable_module(subject).value <= len(dependents)


def test_a_concrete_module_the_repository_leans_on_sits_in_the_zone_of_pain() -> None:
    """Thirty dependents and no contract is the corner, and either half alone is not."""
    painful = fact(afferent=30, efferent=1, types=40)
    abstract = fact(afferent=30, efferent=1, types=40, abstract=40)
    lonely = fact(afferent=0, efferent=1, types=40)

    assert painful.distance == pytest.approx(0.967741935)
    assert concrete_module_the_repository_leans_on(painful).value
    assert not concrete_module_the_repository_leans_on(abstract).value
    assert not concrete_module_the_repository_leans_on(lonely).value


def test_the_two_settings_decide_how_depended_upon_and_how_far_out_a_module_has_to_be() -> None:
    """Two dependents at `D = 0.75` is under one default and over the other, so each is checked."""
    subject = fact(afferent=2, efferent=0, types=4, abstract=1)

    assert subject.distance == 0.75
    assert not concrete_module_the_repository_leans_on(subject).value
    assert concrete_module_the_repository_leans_on(subject, minimum_dependents=2).value
    assert not concrete_module_the_repository_leans_on(
        subject, minimum_dependents=2, minimum_distance=0.8
    ).value


def test_the_abstract_side_of_the_main_sequence_is_never_reported_as_the_concrete_one() -> None:
    """`D` is a magnitude with no direction, so the side has to be tested separately.

    Both modules here sit exactly `0.75` from the line. One is entirely contracts and depends on
    nine modules, the other is entirely implementations and nine modules depend on it, and only
    the second is the change amplifier this rule is about.
    """
    scaffolding = fact(afferent=3, efferent=9, types=2, abstract=2)
    amplifier = fact(afferent=9, efferent=3, types=4)

    assert (scaffolding.distance, amplifier.distance) == (0.75, 0.75)
    assert not concrete_module_the_repository_leans_on(scaffolding).value
    assert concrete_module_the_repository_leans_on(amplifier).value


def test_an_abstraction_nothing_imports_is_scaffolding_and_one_with_callers_is_not() -> None:
    """Both halves are required, and each one alone leaves the module alone."""
    unused = fact(afferent=0, efferent=1, types=2, abstract=2)
    implemented = fact(afferent=6, efferent=1, types=2, abstract=2)
    concrete = fact(afferent=0, efferent=1, types=2)

    assert abstraction_nothing_depends_on(unused)
    assert not abstraction_nothing_depends_on(implemented)
    assert not abstraction_nothing_depends_on(concrete)


def test_a_half_abstract_module_is_judged_against_the_share_the_project_states() -> None:
    """One contract among four types is scaffolding only where the project says it is."""
    subject = fact(afferent=0, efferent=1, types=4, abstract=1)

    assert subject.abstractness == 0.25
    assert not abstraction_nothing_depends_on(subject)
    assert abstraction_nothing_depends_on(subject, minimum_abstractness=0.25)


def test_a_module_of_plain_functions_that_nothing_imports_is_left_alone() -> None:
    """A leaf with no types has an abstractness of zero, which is never a missing implementer."""
    assert not abstraction_nothing_depends_on(fact(efferent=2))


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
        "from abc import ABC, abstractmethod\n\n\n"
        "class Codec(ABC):\n"
        "    @abstractmethod\n"
        "    def encode(self) -> str: ...\n\n\n"
        "class Frame:\n    width = 1\n\n\n"
        "class Packet:\n    size = 2\n\n\n"
        "class Header:\n    kind = 3\n"
    )
    (package / "reader.py").write_text(
        "from pkg.core import Frame\n\n\n"
        "class Reader:\n    frame = Frame\n\n\n"
        "class Buffer:\n    depth = 4\n"
    )
    (package / "writer.py").write_text(
        "from pkg.core import Packet\nfrom pkg.reader import Reader\n\n\n"
        "def write(reader: Reader) -> Packet:\n    return Packet()\n"
    )
    return tmp_path


@cache
def built(root: str) -> tuple[ModuleCouplingFact, ...]:
    """Return the coupling facts this kernel builds for one repository root."""
    workspace = Kernel(binary=BINARY, root=Path(root)).build(
        ["ModuleCouplingFact"], {"ModuleCouplingFact": ModuleCouplingFact}
    )
    return tuple(workspace.stream(ModuleCouplingFact))


def named(facts: tuple[ModuleCouplingFact, ...], module: str) -> ModuleCouplingFact:
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

    assert (core.afferent_count, core.efferent_count) == (2, 0)
    assert (reader.afferent_count, reader.efferent_count) == (1, 1)
    assert (writer.afferent_count, writer.efferent_count) == (0, 2)
    assert (core.declaration_count, core.abstract_declaration_count) == (4, 1)
    assert (reader.declaration_count, reader.abstract_declaration_count) == (2, 0)
    assert (writer.declaration_count, writer.abstract_declaration_count) == (0, 0)
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

    assert [dependency_on_a_less_stable_module(item).value for item in facts] == [0, 0, 0, 0]
    assert not any(concrete_module_the_repository_leans_on(item).value for item in facts)
    assert not any(abstraction_nothing_depends_on(item) for item in facts)


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
def test_an_arrow_from_the_settled_module_to_the_volatile_one_is_reported(
    inverted: Path,
) -> None:
    """No layer was named anywhere, and the layering violation is found from the graph alone."""
    facts = built(str(inverted))
    core = named(facts, "pkg.core")
    writer = named(facts, "pkg.writer")

    assert (core.afferent_count, core.efferent_count) == (1, 1)
    assert (writer.afferent_count, writer.efferent_count) == (1, 1)
    assert core.instability == 0.5
    assert writer.instability == 0.5
    assert dependency_on_a_less_stable_module(core).value == 0
    assert dependency_on_a_less_stable_module(core, tolerance=-0.1).value == 1


@cache
def oracle(root: str) -> list[dict[str, str | float]]:
    """Return the Stable Dependencies violations Archy reports for one source tree.

    Archy is the fork this metric was ported out of, so it is the oracle for the notion the two
    share. It is asked through its own command line with a configuration that declares one layer
    and forbids nothing, which leaves the Stable Dependencies check as the only thing it answers.
    """
    configuration = Path(root).parent / "archy-sdp.yaml"
    configuration.write_text(
        "layers:\n  everything:\n    modules:\n      - mcmr.**\nforbid: []\n"
        "sdp:\n  enabled: true\n  tolerance: 0.0\n  mode: warn\n"
    )
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--quiet",
            "--extra",
            "parser",
            "archy",
            "check",
            root,
            "--config",
            str(configuration),
            "--format",
            "json",
        ],
        cwd=ARCHY,
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return json.loads(completed.stdout)["sdp_violations"]


@pytest.fixture(scope="session")
def snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy this project's own source so both producers read exactly the same bytes."""
    copied = tmp_path_factory.mktemp("coupling") / "src"
    shutil.copytree(SOURCE, copied, ignore=shutil.ignore_patterns("__pycache__"))
    return copied


@needs_kernel
@needs_archy
def test_every_violation_this_rule_reports_is_one_archy_reports_too(snapshot: Path) -> None:
    """Containment rather than equality, and the gap has a stated cause rather than a tolerance.

    Both readers compute `I` the same way from the same import graph, so the only thing that can
    separate them is which edges the graph holds. MCMR leaves an import stated only inside a
    `TYPE_CHECKING` block out, because it does not exist when the program runs, and Archy keeps
    it. Those edges raise the efferent count of the module stating them, which raises its `I`, and
    a target whose `I` was raised past its importer's becomes a violation there and not here.

    So the relation is one way. Every violation MCMR reports is one Archy reports, and every
    violation only Archy reports involves a module whose two readings of `I` differ.
    """
    facts = built(str(snapshot))
    ours = {
        (item.module, dependency.module)
        for item in facts
        for dependency in item.dependencies
        if dependency.instability > item.instability
    }
    theirs = {(str(row["source"]), str(row["target"])) for row in oracle(str(snapshot))}
    stated = {item.module: item.instability for item in facts}
    disagreed = {
        str(row["source"])
        for row in oracle(str(snapshot))
        if stated[str(row["source"])] != row["source_instability"]
    } | {
        str(row["target"])
        for row in oracle(str(snapshot))
        if stated[str(row["target"])] != row["target_instability"]
    }

    assert theirs
    assert ours
    assert ours <= theirs
    assert all(source in disagreed or target in disagreed for source, target in theirs - ours)
    assert sum(dependency_on_a_less_stable_module(item).value for item in facts) == len(ours)


@needs_kernel
@needs_archy
def test_instability_agrees_with_archy_wherever_the_two_graphs_hold_the_same_edges(
    snapshot: Path,
) -> None:
    """The metric itself is not in dispute, which is what makes the edge difference legible.

    Archy reports `I` for both ends of every violation it finds. On this source that is six
    readings, and the ones where the two graphs agree on the edges have to agree exactly, since
    the formula has one answer. Anything left over is a module holding a `TYPE_CHECKING` import,
    which the test proves by finding that import in the source rather than by assuming it.
    """
    stated = {item.module: item.instability for item in built(str(snapshot))}
    readings = {
        (str(row[side]), float(row[f"{side}_instability"]))
        for row in oracle(str(snapshot))
        for side in ("source", "target")
    }
    apart = {module for module, reading in readings if stated[module] != reading}

    assert readings
    assert len(apart) < len(readings)
    for module in apart:
        source = (snapshot / f"{module.replace('.', '/')}.py").read_text()
        assert "if TYPE_CHECKING:" in source
