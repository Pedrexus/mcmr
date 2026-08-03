import json
from pathlib import Path

import pytest
from patos import FrozenModel

from mcmr.commands.projection import imports, proposed
from mcmr.commands.projection import simulate as simulate_command
from mcmr.structure.change import (
    ImportProposal,
    ProposedImport,
    SimulationFormat,
    SimulationText,
    propagation,
)
from mcmr.structure.projections import Dependency, JsonRendering, ModuleGraph

from ..support import kernel_binary, needs_kernel


def chain() -> ModuleGraph:
    """Build a layered repository where `cli` imports `engine` imports `store`."""
    return ModuleGraph(
        root=Path("/repository"),
        paths={
            "pkg": "pkg/__init__.py",
            **{f"pkg.{name}": f"pkg/{name}.py" for name in ("cli", "engine", "store")},
        },
        dependencies=(
            Dependency(importer="pkg.cli", imported="pkg.engine", path="pkg/cli.py", lines=(1,)),
            Dependency(
                importer="pkg.engine", imported="pkg.store", path="pkg/engine.py", lines=(1,)
            ),
        ),
    )


def repository(root: Path) -> Path:
    """Write the same layered package on disk, so both readers see one tree."""
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "store.py").write_text("import json\n\n\ndef load():\n    return json.dumps({})\n")
    (package / "engine.py").write_text(
        "from .store import load\n\n\ndef run():\n    return load()\n"
    )
    (package / "cli.py").write_text("from .engine import run\n\n\ndef main():\n    return run()\n")
    return root


class Oracle(FrozenModel):
    """Archy output frozen at commit `408679b`, limited to claims MCMR also makes.

    Archy also reports a composite score and layer rules, and MCMR has neither, so only the three
    answers both tools define the same way over the same graph are retained.
    """

    cycles: list[list[str]] = []
    back_edges: list[tuple[str, str]] = []
    before: float = 0.0
    after: float = 0.0


def test_an_import_the_repository_does_not_hold_yet_closes_a_loop() -> None:
    """The question a proposal answers is whether this edit would tangle the repository."""
    proposal = ImportProposal(
        graph=chain(), added=(ProposedImport(importer="pkg.store", imported="pkg.cli"),)
    )

    simulation = proposal.run()

    assert [cycle.members for cycle in simulation.cycles_formed] == [
        ["pkg.cli", "pkg.engine", "pkg.store"]
    ]
    assert simulation.cycles_broken == []
    assert [(item.importer, item.imported) for item in simulation.back_edges_formed] == [
        ("pkg.store", "pkg.cli")
    ]
    assert simulation.propagation_before == 0.4375
    assert simulation.propagation_after == 0.625


def test_removing_an_import_can_break_a_loop_the_repository_already_has() -> None:
    """The same question runs the other way, which is what a refactoring is checked against."""
    tangled = chain().model_copy(
        update={
            "dependencies": (
                *chain().dependencies,
                Dependency(
                    importer="pkg.store", imported="pkg.cli", path="pkg/store.py", lines=(1,)
                ),
            )
        }
    )
    proposal = ImportProposal(
        graph=tangled, removed=(ProposedImport(importer="pkg.store", imported="pkg.cli"),)
    )

    simulation = proposal.run()

    assert [cycle.members for cycle in simulation.cycles_broken] == [
        ["pkg.cli", "pkg.engine", "pkg.store"]
    ]
    assert simulation.cycles_formed == []
    assert [(item.importer, item.imported) for item in simulation.back_edges_cleared] == [
        ("pkg.store", "pkg.cli")
    ]
    assert simulation.propagation_after < simulation.propagation_before


def test_nothing_the_graph_cannot_apply_is_applied_silently() -> None:
    """A report that dropped half the question would answer a question nobody asked."""
    proposal = ImportProposal(
        graph=chain(),
        added=(
            ProposedImport(importer="pkg.cli", imported="pkg.engine"),
            ProposedImport(importer="pkg.cli", imported="pkg.missing"),
            ProposedImport(importer="pkg.store", imported="pkg.cli"),
        ),
        removed=(
            ProposedImport(importer="pkg.store", imported="pkg.cli"),
            ProposedImport(importer="pkg.engine", imported="pkg.cli"),
        ),
    )

    applied = proposal.resolve()

    assert applied.added == []
    assert applied.removed == []
    assert [(item.importer, item.imported) for item in applied.unchanged] == [
        ("pkg.cli", "pkg.engine"),
        ("pkg.engine", "pkg.cli"),
    ]
    assert [(item.importer, item.imported) for item in applied.cancelled] == [
        ("pkg.store", "pkg.cli")
    ]
    assert applied.unknown == ["pkg.missing"]
    assert proposal.run().cycles_formed == []


def test_the_same_import_asked_for_twice_is_one_import() -> None:
    """A caller repeating itself is asking one question, and a graph holds one edge."""
    proposal = ImportProposal(
        graph=chain(),
        added=(
            ProposedImport(importer="pkg.store", imported="pkg.cli"),
            ProposedImport(importer="pkg.store", imported="pkg.cli"),
        ),
    )

    applied = proposal.resolve()

    assert len(applied.added) == 1
    assert len(proposal.hypothetical(applied).dependencies) == 3


def test_the_propagation_cost_reads_the_reach_of_every_module() -> None:
    """A repository nothing imports twice costs less to edit than one everything reaches."""
    assert propagation(ModuleGraph(root=Path("/repository"))) == 0.0
    assert propagation(chain()) == 0.4375


def test_an_import_reads_as_the_pair_it_names() -> None:
    """A module name never holds a colon, so a colon is what separates the two ends."""
    assert ProposedImport.parse("pkg.a:pkg.b") == ProposedImport(
        importer="pkg.a", imported="pkg.b"
    )
    assert proposed(" pkg.a:pkg.b , pkg.c:pkg.d ") == [
        ProposedImport(importer="pkg.a", imported="pkg.b"),
        ProposedImport(importer="pkg.c", imported="pkg.d"),
    ]
    assert proposed("") == []
    with pytest.raises(ValueError, match="importer:imported"):
        ProposedImport.parse("pkg.a")
    with pytest.raises(ValueError, match="importer:imported"):
        ProposedImport.parse("pkg.a:")


def test_the_simulation_text_names_every_section_and_bounds_each_one() -> None:
    """A reader wants what was applied, what it would do, and what it would cost."""
    branched = chain().model_copy(
        update={
            "paths": {**chain().paths, "pkg.util": "pkg/util.py"},
            "dependencies": (
                *chain().dependencies,
                Dependency(importer="pkg.cli", imported="pkg.util", path="pkg/cli.py", lines=(2,)),
            ),
        }
    )
    proposal = ImportProposal(
        graph=branched,
        added=(
            ProposedImport(importer="pkg.store", imported="pkg.cli"),
            ProposedImport(importer="pkg.store", imported="pkg.util"),
            ProposedImport(importer="pkg.cli", imported="pkg.engine"),
            ProposedImport(importer="pkg.cli", imported="pkg.gone"),
        ),
        removed=(ProposedImport(importer="pkg.cli", imported="pkg.util"),),
    )

    rendered = SimulationText(limit=1).render(proposal.run())

    expected = [
        "2 imports added and 1 removed, in the graph alone, with no file touched",
        "propagation cost 0.3600 becomes ",
        "Added (2)\n  pkg.store imports pkg.cli\n  and 1 more",
        "Removed (1)\n  pkg.cli imports pkg.util",
        "Already as asked (1)\n  pkg.cli imports pkg.engine",
        "Stated both ways (0)",
        "Unknown modules (1)\n  pkg.gone",
        "Cycles formed (1)",
        "Cycles broken (0)",
        "Back edges formed (1)",
        "Back edges cleared (0)",
    ]
    for section in expected:
        assert section in rendered


def test_the_format_chooses_the_rendering_for_a_simulation() -> None:
    """A new format is a member and a class of its own, never a change to the traversal."""
    simulation = ImportProposal(graph=chain()).run()

    assert isinstance(SimulationFormat.TEXT.simulation(5), SimulationText)
    assert isinstance(SimulationFormat.JSON.simulation(5), JsonRendering)
    assert (
        json.loads(SimulationFormat.JSON.simulation(5).render(simulation))["propagation_before"]
        == 0.4375
    )


def test_two_simulations_of_the_same_proposal_render_the_same_bytes() -> None:
    """A prediction a reader compares between edits has to hold still on unchanged input."""
    proposal = ImportProposal(
        graph=chain(), added=(ProposedImport(importer="pkg.store", imported="pkg.cli"),)
    )
    runs = [proposal.run() for _ in range(2)]

    assert SimulationText().render(runs[0]) == SimulationText().render(runs[1])
    assert JsonRendering().render(runs[0]) == JsonRendering().render(runs[1])


@needs_kernel
def test_the_simulate_command_answers_over_a_real_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr simulate` reads the same graph every other projection reads."""
    root = repository(tmp_path)

    simulate_command(root, add="pkg.store:pkg.cli", kernel=kernel_binary())
    assert "Cycles formed (1)\n  pkg.cli pkg.engine pkg.store" in capsys.readouterr().out

    simulate_command(
        root,
        add="pkg.store:pkg.cli",
        format=SimulationFormat.JSON,
        kernel=kernel_binary(),
    )
    written = json.loads(capsys.readouterr().out)
    assert written["propagation_after"] > written["propagation_before"]


@needs_kernel
def test_the_simulation_agrees_with_the_archy_oracle_on_the_same_edge(tmp_path: Path) -> None:
    """Archy answers the same structural question, so its answer is the one MCMR owes.

    Cycles, back edges, and propagation cost are all defined the same way in both tools, over the
    same import graph, so every one of them has to agree exactly. The score and the layer rules
    Archy also reports have no MCMR counterpart and are not compared.
    """
    root = repository(tmp_path)
    ours = ImportProposal(
        graph=imports(root, kernel_binary()),
        added=(ProposedImport(importer="pkg.store", imported="pkg.cli"),),
    ).run()
    theirs = Oracle(
        cycles=[["pkg.cli", "pkg.engine", "pkg.store"]],
        back_edges=[("pkg.store", "pkg.cli")],
        before=0.4375,
        after=0.625,
    )

    assert [sorted(cycle.members) for cycle in ours.cycles_formed] == [
        sorted(cycle) for cycle in theirs.cycles
    ]
    assert ours.propagation_before == theirs.before
    assert ours.propagation_after == theirs.after
    assert [(item.importer, item.imported) for item in ours.back_edges_formed] == list(
        theirs.back_edges
    )


@needs_kernel
def test_the_simulation_agrees_with_the_archy_oracle_on_removing_an_edge(tmp_path: Path) -> None:
    """The same agreement has to hold the other way, or only half the answer is trustworthy."""
    root = repository(tmp_path)
    ours = ImportProposal(
        graph=imports(root, kernel_binary()),
        removed=(ProposedImport(importer="pkg.engine", imported="pkg.store"),),
    ).run()
    theirs = Oracle(before=0.4375, after=0.3125)

    assert ours.propagation_before == theirs.before
    assert ours.propagation_after == theirs.after
    assert ours.cycles_formed == []
    assert theirs.cycles == []
