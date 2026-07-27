from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cyclopts import App
from rich.console import Console
from rich.table import Table

from .benchmark import FloorBenchmark
from .catalog import Catalog
from .comparisons import Incomparable, ReportFormat, RunComparison, RunSeries
from .diagrams import DiagramBuilder, DiagramFormat, DiagramKind, DiagramRenderer
from .discovery import RuleModuleDiscovery
from .facts import Fact, SymbolReach, SymbolReachFact, Visibility
from .influence import InfluenceReport
from .kernel import VENDORED, Kernel, locate
from .policy import Profile, profiles
from .projections import ModuleGraph, ProjectionFormat
from .reports import CheckFormat, CheckReport
from .repository import GraphReader
from .runs import GitIdentity, Judgment, RunStore, allowed
from .simulation import ImportProposal, ProposedImport, SimulationFormat
from .upstream import ClaimIndex, ToolCoverage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models import RuleDefinition

app = App(name="mcmr", help="Define and enforce the engineering rules that make your code yours.")
# Emoji substitution is off because every diagnostic this tool prints is a colon-delimited
# location. Left on, `tile_merge.cuh:100:1` renders as `tile_merge.cuh` followed by a glyph, and no
# editor or CI parser can open what it names. A tool meant to be read by an agent cannot rewrite
# its own coordinates.
console = Console(emoji=False)


@app.command
def check(
    root: Path = Path(),
    *,
    profile: str = "standard",
    select: str = "",
    suffixes: str = "",
    exclude: str = "",
    kernel: Path | None = None,
    format: CheckFormat = CheckFormat.FULL,
    limit: int = 20,
) -> None:
    """Run the catalog over a repository and judge it against one strictness profile.

    root: repository to analyze.
    profile: `relaxed`, `standard`, or `strict`.
    select: substring that narrows the selected rules by callable.
    suffixes: comma-separated source suffixes, for a repository in another language.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    format: `full` for the diagnostic with its source quoted, `concise` for one line each.
    limit: how many failures the report shows.
    """
    report = CheckReport.of(root, judgment(root, profile, select, suffixes, exclude, kernel).run())
    console.print(
        format.check(limit).render(report), markup=False, highlight=False, soft_wrap=True
    )
    if report.failures:
        raise SystemExit(1)


def judgment(
    root: Path, profile: str, select: str, suffixes: str, exclude: str, kernel: Path | None
) -> Judgment:
    """Build the one pass of the engine that every command judging a repository runs."""
    return Judgment(
        binary=kernel or locate(Path(__file__).parents[2]),
        root=root,
        profile=profiles()[profile],
        select=select,
        suffixes=tuple(suffix.strip() for suffix in suffixes.split(",") if suffix.strip()),
        exclude=VENDORED + globs(exclude),
    )


def allowance(profile: Profile, definition: RuleDefinition) -> str:
    """Render what the profile allows for one rule, for the report."""
    return allowed(profile.policy(definition))


def globs(exclude: str) -> tuple[str, ...]:
    """Return the extra patterns one command was asked to skip, on top of the defaults."""
    return tuple(pattern.strip() for pattern in exclude.split(",") if pattern.strip())


@app.command
def graph(
    root: Path = Path(),
    *,
    exclude: str = "",
    kernel: Path | None = None,
    limit: int = 15,
) -> None:
    """Show how the declarations of a repository reach each other.

    root: repository to analyze.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    limit: how many rows each section shows.
    """
    client = Kernel(
        binary=kernel or locate(Path(__file__).parents[2]),
        root=root,
        exclude=VENDORED + globs(exclude),
    )
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
    console.print(spread_table("Reaching the most packages", public, limit))
    console.print(
        locality_table(
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
        locality_table(
            "Public and reached by nothing",
            [
                pair
                for pair in public
                if pair[1].other_file_references == 0 and pair[1].own_file_references == 0
            ],
            limit,
        )
    )


def spread_table(title: str, pairs: Sequence[tuple[Fact, SymbolReach]], limit: int) -> Table:
    """Render the declarations whose use spreads the widest."""
    table = Table(title=title)
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


def locality_table(title: str, pairs: Sequence[tuple[Fact, SymbolReach]], limit: int) -> Table:
    """Render one group of declarations beside the module that states them."""
    table = Table(title=f"{title} ({len(pairs)})")
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
    exclude: str = "",
    kernel: Path | None = None,
) -> None:
    """Draw the classes or the packages of a repository, in D2 or in Mermaid.

    root: repository to analyze.
    kind: `class` for the classes and what they inherit, `package` for the modules they import.
    format: `d2` or `mermaid`.
    output: file to write, otherwise the diagram goes to standard output.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    repository = GraphReader(
        binary=kernel or locate(Path(__file__).parents[2]),
        root=root,
        exclude=VENDORED + globs(exclude),
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


@app.command
def coverage(*, tool: str = "pylint", group: str = "", state: str = "", limit: int = 0) -> None:
    """Show what MCMR does about every rule one upstream tool ships.

    tool: the registered tool inventory to account for, such as `pylint` or `clang-tidy`.
    group: narrow to one of that tool's own groups, such as `classes` or `flake8-bugbear`.
    state: narrow to `native`, `delegated`, `adapted`, `inapplicable`, or `unavailable`.
    limit: how many rows to show, or every row by default.
    """
    report = ToolCoverage(
        tool=tool,
        claims=ClaimIndex(
            definitions=tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)
        ),
    )
    entries = [
        entry for entry in report.entries if group in entry.rule.group and state in entry.coverage
    ]
    languages = ", ".join(language.value for language in report.profile.languages)
    table = Table(
        title=f"MCMR against {report.profile.name} for {languages}, {len(entries)} rules"
    )
    for column in ("Rule", "Group", "State", "Answered by"):
        table.add_column(column)
    for entry in entries[: limit or len(entries)]:
        table.add_row(
            " ".join(word for word in (entry.rule.code, entry.rule.symbol) if word),
            entry.rule.group,
            entry.coverage,
            ", ".join(entry.rules),
        )
    console.print(table)
    tally = report.tally()
    console.print(
        " ".join(f"{state}={count}" for state, count in tally.items())
        + f", {sum(tally.values())} accounted for",
        soft_wrap=True,
    )


@app.command
def influence(*, kind: str = "", limit: int = 0) -> None:
    """Show which sources shaped MCMR, the most referenced first.

    kind: narrow to `book`, `paper`, `standard`, `language`, `documentation`, `article`, or `tool`.
    limit: how many rows to show, or every row by default.
    """
    report = InfluenceReport(
        index=ClaimIndex(
            definitions=tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)
        )
    )
    rows = [row for row in report.rows if kind in row.kind]
    table = Table(title=f"What shaped MCMR, {len(rows)} sources")
    for column in ("Source", "Kind", "Author", "References", "Rules"):
        table.add_column(column)
    for row in rows[: limit or len(rows)]:
        table.add_row(row.source, row.kind, row.author, str(row.references), str(row.rules))
    console.print(table)
    tally = report.tally()
    console.print(
        " ".join(f"{name}={count}" for name, count in tally.items())
        + f", {sum(row.references for row in report.rows)} references from"
        + f" {len(report.index.definitions)} rules",
        soft_wrap=True,
    )


@app.command
def floor(
    *,
    samples: int = 9,
    facts: int = 1000,
    output: Path | None = None,
) -> None:
    """Measure the mocked Python framework floor.

    samples: bounded repeated measurements.
    facts: synthetic facts supplied to each rule.
    output: optional JSON report path.
    """
    report = FloorBenchmark(samples=samples, fact_count=facts).run()
    table = Table(title="MCMR mock framework floor")
    table.add_column("Boundary")
    table.add_column("Milliseconds", justify="right")
    measurements = {
        "Cold discovery": report.cold_discovery_nanoseconds,
        "Warm discovery": report.warm_discovery_nanoseconds,
        "Median planning": report.median_planning_nanoseconds,
        "Median execution": report.median_execution_nanoseconds,
        "Median fix planning": report.median_fix_planning_nanoseconds,
        "Median total": report.median_total_nanoseconds,
    }
    for name, nanoseconds in measurements.items():
        table.add_row(name, f"{nanoseconds / 1_000_000:.3f}")
    console.print(table)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n")


@app.command
def matrix(
    root: Path = Path(),
    *,
    format: ProjectionFormat = ProjectionFormat.TEXT,
    limit: int = 32,
    exclude: str = "",
    kernel: Path | None = None,
) -> None:
    """Project the imports of a repository as a design structure matrix.

    root: repository to analyze.
    format: `text` for the terminal grid, or `json` for another tool to read.
    limit: how many modules the text grid holds, since a wider one reads as noise.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    projection = imports(root, exclude, kernel).matrix()
    console.print(
        format.matrix(limit).render(projection), markup=False, highlight=False, soft_wrap=True
    )


@app.command
def impact(
    root: Path = Path(),
    *,
    changed: str,
    format: ProjectionFormat = ProjectionFormat.TEXT,
    exclude: str = "",
    kernel: Path | None = None,
) -> None:
    """Report the modules a change to these files could break.

    root: repository to analyze.
    changed: comma-separated paths this change touches.
    format: `text` for a reader, or `json` for another tool to read.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    """
    touched = [Path(path.strip()) for path in changed.split(",") if path.strip()]
    projection = imports(root, exclude, kernel).impact(touched)
    console.print(
        format.impact().render(projection), markup=False, highlight=False, soft_wrap=True
    )


def imports(root: Path, exclude: str, kernel: Path | None) -> ModuleGraph:
    """Read the repository graph and keep the modules and the imports both projections read."""
    repository = GraphReader(
        binary=kernel or locate(Path(__file__).parents[2]),
        root=root,
        exclude=VENDORED + globs(exclude),
    ).read()
    return ModuleGraph.of(repository, root)


@app.command
def snapshot(
    root: Path = Path(),
    *,
    profile: str = "standard",
    select: str = "",
    suffixes: str = "",
    exclude: str = "",
    kernel: Path | None = None,
    output: Path | None = None,
) -> None:
    """Record what the catalog concludes about a repository, so a later run can be held to it.

    root: repository to analyze.
    profile: `relaxed`, `standard`, or `strict`.
    select: substring that narrows the selected rules by callable.
    suffixes: comma-separated source suffixes, for a repository in another language.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    output: file to write, otherwise the run joins the store under `.mcmr/runs`.
    """
    judged = judgment(root, profile, select, suffixes, exclude, kernel).run()
    record = judged.record(GitIdentity(root=root).read(datetime.now(UTC)))
    target = output
    if target is None:
        target = RunStore(directory=root / ".mcmr").write(record)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(record.model_dump_json(indent=2) + "\n")
    console.print(
        f"recorded {len(record.rules)} rules, {record.failing_count} failing sites in "
        f"{record.failing_rule_count} rules, {record.unassessed_count} unassessed, over "
        f"{record.stats.file_count} files at {record.identity.label} in {target}",
        soft_wrap=True,
    )


@app.command
def diff(
    root: Path = Path(),
    *,
    profile: str = "standard",
    baseline: Path | None = None,
    current: Path | None = None,
    select: str = "",
    suffixes: str = "",
    exclude: str = "",
    kernel: Path | None = None,
    format: ReportFormat = ReportFormat.TEXT,
    limit: int = 10,
) -> None:
    """Hold a repository against a run it recorded earlier and say which way it moved.

    root: repository to analyze.
    profile: `relaxed`, `standard`, or `strict`, which both runs have to share.
    baseline: recorded run to compare against, otherwise the newest one under this profile.
    current: recorded run to compare, otherwise the repository is judged as it stands now.
    select: substring that narrows the selected rules by callable.
    suffixes: comma-separated source suffixes, for a repository in another language.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    format: `text` for a reader, or `json` for another tool to read.
    limit: how many rules each section names.
    """
    store = RunStore(directory=root / ".mcmr")
    recorded = store.read(baseline) if baseline is not None else store.latest(profile)
    if recorded is None:
        console.print(
            f"nothing recorded under the {profile} profile in {store.runs}, "
            f"so run `mcmr snapshot {root}` first",
            soft_wrap=True,
        )
        raise SystemExit(2)
    judged = (
        store.read(current)
        if current is not None
        else judgment(root, profile, select, suffixes, exclude, kernel)
        .run()
        .record(GitIdentity(root=root).read(datetime.now(UTC)))
    )
    try:
        comparison = RunComparison.between(recorded, judged)
    except Incomparable as refusal:
        console.print(str(refusal), soft_wrap=True)
        raise SystemExit(2) from refusal
    console.print(
        format.comparison(limit).render(comparison),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    if comparison.regressed:
        raise SystemExit(1)


@app.command
def trend(
    root: Path = Path(),
    *,
    profile: str = "standard",
    last: int = 10,
    format: ReportFormat = ReportFormat.TEXT,
) -> None:
    """Show the direction a repository moved across the runs it has recorded.

    root: repository whose recorded runs are read.
    profile: `relaxed`, `standard`, or `strict`, since a line through two of them means nothing.
    last: how many of the most recent runs the view holds.
    format: `text` for a reader, or `json` for another tool to read.
    """
    series = RunSeries.of(RunStore(directory=root / ".mcmr").records(), profile, last)
    console.print(format.series().render(series), markup=False, highlight=False, soft_wrap=True)


@app.command
def simulate(
    root: Path = Path(),
    *,
    add: str = "",
    remove: str = "",
    format: SimulationFormat = SimulationFormat.TEXT,
    exclude: str = "",
    kernel: Path | None = None,
    limit: int = 10,
) -> None:
    """Ask what these imports would do to the shape of a repository, without editing a file.

    root: repository to analyze.
    add: comma-separated `importer:imported` pairs to answer as though they existed.
    remove: comma-separated `importer:imported` pairs to answer as though they were gone.
    format: `text` for a reader, or `json` for another tool to read.
    exclude: extra comma-separated globs, on top of the vendored and build defaults.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    limit: how many entries each section names.
    """
    proposal = ImportProposal(
        graph=imports(root, exclude, kernel),
        added=proposed(add),
        removed=proposed(remove),
    )
    console.print(
        format.simulation(limit).render(proposal.run()),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def proposed(specification: str) -> tuple[ProposedImport, ...]:
    """Read every `importer:imported` pair one option states."""
    return tuple(
        ProposedImport.parse(item.strip()) for item in specification.split(",") if item.strip()
    )


if __name__ == "__main__":
    app()
