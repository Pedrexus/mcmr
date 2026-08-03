import json
from pathlib import Path

from ...accounting.replacement import Ge4mReplacement
from ...accounting.upstream import ClaimIndex, ToolCoverage, ToolRegistry
from ...audit.influence import InfluenceReport
from ...rulebook.catalog import Catalog
from ...rulebook.discovery import RuleModuleDiscovery
from ..interface import app, console, readable_table
from .coverage import CoveragePresentation


@app.command
def catalog(output: Path | None = None) -> None:
    """Export the live typed rule catalog rather than maintaining a generated registry.

    output: optional JSON path. Standard output receives the document when omitted.
    """
    definitions = Catalog(modules=RuleModuleDiscovery().modules).definitions
    rendered = json.dumps(
        {
            "schema": 1,
            "rules": [definition.model_dump(mode="json") for definition in definitions],
        },
        indent=2,
        sort_keys=True,
    )
    if output is None:
        console.print(rendered, markup=False, highlight=False, soft_wrap=True)
        return
    output.write_text(rendered + "\n", encoding="utf-8")
    console.print(f"exported {len(definitions)} live rules to {output}", soft_wrap=True)


@app.command
def replacement() -> None:
    """Audit every frozen GE4M rule and capability against its declared successor."""
    ledger = Ge4mReplacement.load()
    definitions = list(Catalog(modules=RuleModuleDiscovery().modules).definitions)
    audit = ledger.audit(definitions)
    table = readable_table("GE4M replacement")
    table.add_column("State")
    table.add_column("Capability")
    table.add_column("Replacement")
    for item in ledger.capability_migration.capabilities:
        table.add_row(item.state, item.source_id, item.replacement)
    console.print(table)
    console.print(
        f"{audit.mapped_rules}/{audit.legacy_rules} rules and "
        f"{audit.mapped_capabilities}/{audit.legacy_capabilities} capabilities mapped, "
        f"{audit.missing_capabilities} missing, {len(audit.issues)} ledger issues",
        soft_wrap=True,
    )


@app.command
def coverage(*, tool: str = "all", group: str = "", state: str = "", limit: int = 0) -> None:
    """Show what MCMR does about every rule the inventoried upstream tools ship.

    tool: `all` for one complete summary, or one registered tool such as `pylint` or `clang-tidy`.
    group: narrow to one of that tool's own groups, such as `classes` or `flake8-bugbear`.
    state: narrow to `native`, `delegated`, `adapted`, `inapplicable`, or `unavailable`.
    limit: how many detail rows to show for one tool, or every row by default.
    """
    with console.status("Accounting for upstream inventories", spinner="dots"):
        reports = _coverage_reports(tool)
    CoveragePresentation(group=group, state=state, limit=limit).show(reports)


def _coverage_reports(tool: str) -> list[ToolCoverage]:
    """Build reports for one tool or every inventoried upstream source."""
    claims = ClaimIndex(definitions=Catalog(modules=RuleModuleDiscovery().modules).definitions)
    tools = (
        [profile.slug for profile in ToolRegistry().profiles if profile.inventoried]
        if tool.casefold() == "all"
        else [tool]
    )
    return [ToolCoverage(tool=name, claims=claims) for name in tools]


@app.command
def influence(*, kind: str = "", limit: int = 0) -> None:
    """Show which sources shaped MCMR, the most referenced first.

    kind: narrow to `book`, `paper`, `standard`, `language`, `documentation`, `article`, or `tool`.
    limit: how many rows to show, or every row by default.
    """
    with console.status("Indexing the catalog references", spinner="dots"):
        report = InfluenceReport(
            index=ClaimIndex(
                definitions=Catalog(modules=RuleModuleDiscovery().modules).definitions
            )
        )
    rows = [row for row in report.rows if kind in row.kind]
    table = readable_table(f"What shaped MCMR, {len(rows)} sources")
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
