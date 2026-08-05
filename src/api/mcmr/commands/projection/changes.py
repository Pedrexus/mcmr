from pathlib import Path

from ...project import locate
from ...repository import GraphReader
from ...structure.change import ImportProposal, ProposedImport, SimulationFormat
from ...structure.projections import ModuleGraph, ProjectionFormat
from ..interface import app, console


@app.command
def matrix(
    root: Path = Path(),
    *,
    format: ProjectionFormat = ProjectionFormat.TEXT,
    limit: int = 32,
    kernel: Path | None = None,
) -> None:
    """Project the imports of a repository as a design structure matrix.

    root: repository to analyze.
    format: `text` for the terminal grid, or `json` for another tool to read.
    limit: how many modules the text grid holds, since a wider one reads as noise.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    with console.status("Building the import matrix", spinner="dots"):
        projection = imports(root, kernel).matrix()
    console.print(
        format.matrix(limit).render(projection), markup=False, highlight=False, soft_wrap=True
    )


@app.command
def impact(
    root: Path = Path(),
    *,
    changed: str,
    format: ProjectionFormat = ProjectionFormat.TEXT,
    kernel: Path | None = None,
) -> None:
    """Report the modules a change to these files could break.

    root: repository to analyze.
    changed: comma-separated paths this change touches.
    format: `text` for a reader, or `json` for another tool to read.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    touched = [Path(path.strip()) for path in changed.split(",") if path.strip()]
    with console.status("Tracing the change impact", spinner="dots"):
        projection = imports(root, kernel).impact(touched)
    console.print(
        format.impact().render(projection), markup=False, highlight=False, soft_wrap=True
    )


def imports(root: Path, kernel: Path | None) -> ModuleGraph:
    """Read the repository graph and keep the modules and the imports both projections read."""
    repository = GraphReader(
        binary=kernel or locate(root),
        root=root,
    ).read()
    return ModuleGraph.of(repository, root)


@app.command
def simulate(
    root: Path = Path(),
    *,
    add: str = "",
    remove: str = "",
    format: SimulationFormat = SimulationFormat.TEXT,
    kernel: Path | None = None,
    limit: int = 10,
) -> None:
    """Ask what these imports would do to the shape of a repository, without editing a file.

    root: repository to analyze.
    add: comma-separated `importer:imported` pairs to answer as though they existed.
    remove: comma-separated `importer:imported` pairs to answer as though they were gone.
    format: `text` for a reader, or `json` for another tool to read.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    limit: how many entries each section names.
    """
    with console.status("Simulating the import changes", spinner="dots"):
        proposal = ImportProposal(
            graph=imports(root, kernel),
            added=proposed(add),
            removed=proposed(remove),
        )
        simulation = proposal.run()
    console.print(
        format.simulation(limit).render(simulation),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def proposed(specification: str) -> list[ProposedImport]:
    """Read every `importer:imported` pair one option states."""
    return [
        ProposedImport.parse(item.strip()) for item in specification.split(",") if item.strip()
    ]
