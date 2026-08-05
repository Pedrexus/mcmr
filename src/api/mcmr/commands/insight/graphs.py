from pathlib import Path
from typing import TYPE_CHECKING

from ...facts import Fact, SymbolReach, SymbolReachFact, Visibility
from ...kernel import Kernel
from ...project import locate
from ...repository import GraphReader
from ...structure.diagrams import DiagramBuilder, DiagramFormat, DiagramKind, DiagramRenderer
from ..interface import app, console, readable_table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.table import Table


@app.command
def graph(
    root: Path = Path(),
    *,
    kernel: Path | None = None,
    limit: int = 15,
) -> None:
    """Show how the declarations of a repository reach each other.

    root: repository to analyze.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    limit: how many rows each section shows.
    """
    client = Kernel(
        binary=kernel or locate(root),
        root=root,
    )
    with console.status("Reading the symbol graph", spinner="dots"):
        workspace = client.reach()
    declarations = [
        (fact, item) for fact in workspace.stream(SymbolReachFact) for item in fact.declarations
    ]
    reachable = [
        (fact, item)
        for fact, item in declarations
        if item.kind in {"class", "function", "method", "property"}
    ]
    public = [pair for pair in reachable if pair[1].visibility is Visibility.PUBLIC]
    console.print(
        f"{workspace.stats.file_count} files, {workspace.stats.node_count} nodes, "
        f"{workspace.stats.edge_count} edges, {len(declarations)} declarations, "
        f"{len(public)} public callables and classes, "
        f"graph {workspace.stats.graph_nanoseconds / 1_000_000:.0f} ms"
    )
    console.print(_spread_table("Reaching the most packages", public, limit))
    console.print(
        _locality_table(
            "Public but reached only by their own file",
            [
                pair
                for pair in public
                if pair[1].other_file_references == 0 and pair[1].own_file_references > 0
            ],
            limit,
        )
    )
    console.print(
        _locality_table(
            "Public and reached by nothing",
            [
                pair
                for pair in public
                if pair[1].other_file_references == 0 and pair[1].own_file_references == 0
            ],
            limit,
        )
    )


def _spread_table(title: str, pairs: Sequence[tuple[Fact, SymbolReach]], limit: int) -> Table:
    """Render the declarations whose use spreads the widest."""
    table = readable_table(title)
    for column in ("Declaration", "Kind", "Packages", "Files", "Calls", "Built"):
        table.add_column(
            column, justify="right" if column not in {"Declaration", "Kind"} else "left"
        )
    widest = sorted(pairs, key=lambda pair: -pair[1].referencing_packages)[:limit]
    for _, item in widest:
        table.add_row(
            item.qualname,
            item.kind,
            str(item.referencing_packages),
            str(item.referencing_files),
            str(item.call_count),
            str(item.instantiate_count),
        )
    return table


def _locality_table(title: str, pairs: Sequence[tuple[Fact, SymbolReach]], limit: int) -> Table:
    """Render one group of declarations beside the module that states them."""
    table = readable_table(f"{title} ({len(pairs)})")
    table.add_column("Declaration")
    table.add_column("Kind")
    table.add_column("Module")
    for fact, item in sorted(pairs, key=lambda pair: pair[1].qualname)[:limit]:
        table.add_row(item.qualname, item.kind, fact.span.path)
    return table


@app.command
def diagram(
    root: Path = Path(),
    *,
    kind: DiagramKind = DiagramKind.CLASS,
    format: DiagramFormat = DiagramFormat.D2,
    output: Path | None = None,
    kernel: Path | None = None,
) -> None:
    """Draw the classes or the packages of a repository, in D2 or in Mermaid.

    root: repository to analyze.
    kind: `class` for the classes and what they inherit, `package` for the modules they import.
    format: `d2` or `mermaid`.
    output: file to write, otherwise the diagram goes to standard output.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    with console.status("Building the repository diagram", spinner="dots"):
        repository = GraphReader(
            binary=kernel or locate(root),
            root=root,
        ).read()
        drawing = DiagramBuilder.of(kind).build(repository)
        text = DiagramRenderer.of(format).render(drawing)
    if output is None:
        console.print(text, markup=False, highlight=False, soft_wrap=True)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    console.print(
        f"{len(drawing.nodes)} boxes and {len(drawing.edges)} lines "
        f"in {output}, from {len(repository.nodes)} graph nodes",
        soft_wrap=True,
    )
