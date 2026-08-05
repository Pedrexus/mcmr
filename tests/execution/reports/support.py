from typing import TYPE_CHECKING

from mcmr.domain.contracts import (
    Edit,
    Finding,
    FixPlan,
    FixSafety,
    Remove,
    RuleValue,
)
from mcmr.facts import NodeRef, SourceSpan
from mcmr.presentation.reports import (
    CheckReport,
    RuleFailure,
)
from mcmr.rulebook.catalog import RuleDefinition, RuleDocumentation, RuleIdentity

if TYPE_CHECKING:
    from pathlib import Path

_SOURCE = "def render(value):\n    total = value + 1\n    return total\n"


def span(*, start: int = 1, end: int = 1, first: int = 0, last: int = 10) -> SourceSpan:
    """Return one span over the sample source, in the shape the kernel writes."""
    return SourceSpan(
        path="render.py",
        start_line=start,
        start_column=first,
        end_line=end,
        end_column=last,
    )


def definition(rule: str, *, output: str, unit: str = "") -> RuleDefinition:
    """Return one definition carrying only what a report and a policy read from it."""
    return RuleDefinition(
        identity=identity(rule),
        output=output,
        unit=unit,
        documentation=RuleDocumentation(
            summary="Count what this demonstration counts.",
            definition="A definition long enough to read.",
            examples="A body of `12` lines returns `12`.",
        ),
    )


def identity(rule: str) -> RuleIdentity:
    """Return the stable identity shared by report fixtures."""
    return RuleIdentity(
        id=rule,
        callable=f"mcmr.rules.general.deterministic.demo.r0001.{rule.lower()}",
        scope="general",
        lane="deterministic",
        family="demo",
        fact="ModuleFact",
    )


def failure(finding: Finding | None = None, value: RuleValue = 3) -> RuleFailure:
    """Return one failure carrying at most one finding, for the renderings to print."""
    return RuleFailure(
        rule="ALL-DEMO0001",
        summary="Count what this demonstration counts.",
        where="module:render.py",
        span=span(),
        value=value,
        allowed="<= 0",
        findings=() if finding is None else (finding,),
    )


def report(*failures: RuleFailure, root: Path) -> CheckReport:
    """Return one check report over a written tree, in the shape a rendering reads."""
    return CheckReport(root=str(root), file_count=1, failures=failures)


def write_tree(tmp_path: Path) -> Path:
    """Write the one source file every excerpt in this module quotes."""
    (tmp_path / "render.py").write_text(_SOURCE)
    return tmp_path


def edit(safety: FixSafety) -> Edit:
    """Build one rendered edit promising as much as the safety level it was given."""
    node = NodeRef(id="render.py:0:import", span=span(), kind="import", text="import os")
    return Edit(
        plan=FixPlan(summary="Remove the import.", rewrites=[Remove(target=node)]),
        safety=safety,
    )
