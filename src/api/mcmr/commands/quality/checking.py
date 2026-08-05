from pathlib import Path
from typing import TYPE_CHECKING, Never

from ...checking.session import allowed
from ...domain.contracts import FixSafety
from ...execution.providers import ProviderExecutionError
from ...presentation import (
    CheckReport,
    FixResult,
    FixSession,
    PythonFixRenderer,
    RichCheck,
)
from ...presentation.reports import CheckFormat
from ...project import ExecutionOverride, MCMRConfiguration, locate
from ..interface import (
    FixPresentation,
    RepairMode,
    RuleCoverage,
    app,
    console,
)
from .analysis import Judgment

if TYPE_CHECKING:
    from ...domain.policy import RulePolicies
    from ...rulebook.catalog import RuleDefinition


@app.command
def check(
    root: Path = Path(),
    *,
    select: str = "",
    suffixes: str = "",
    kernel: Path | None = None,
    format: CheckFormat = CheckFormat.RICH,
    limit: int = 20,
    repair: RepairMode = RepairMode.NONE,
    maximum_fixes: int = 100,
    output: Path | None = None,
    report_only: bool = False,
    deterministic: bool | None = None,
    contextual: bool | None = None,
    external: bool | None = None,
    rule_coverage: RuleCoverage = RuleCoverage.AVAILABLE,
) -> None:
    """Run the catalog over a repository and judge it against each rule's effective policy.

    root: repository to analyze.
    select: substring that narrows the selected rules by callable.
    suffixes: comma-separated source suffixes, for a repository in another language.
    kernel: explicit kernel binary, otherwise the one built from this checkout.
    format: `rich` for structured detail, `full` for plain diagnostics, `concise` for one line,
        or `json` for the complete machine-readable report.
    limit: how many detailed diagnostics the report shows.
    repair: `preview` available patches, `apply` safe plans, or `apply-review` review plans
        through verified fixpoints.
    maximum_fixes: bound the number of verified edits in one run.
    output: optional path that receives the complete JSON report.
    report_only: report failures without returning a failing process status.
    deterministic: enable or disable rules computed from repository facts.
    contextual: enable or disable rules estimated by the configured contextual backend.
    external: permit enabled rules to collect current network evidence in memory.
    rule_coverage: use `all` to fail when any selected rule could not execute.
    """
    overrides = {
        None: ExecutionOverride.UNCHANGED,
        True: ExecutionOverride.ENABLED,
        False: ExecutionOverride.DISABLED,
    }
    analysis = judgment(
        root,
        select=select,
        suffixes=suffixes,
        kernel=kernel,
        failure_limit=None,
        deterministic=overrides[deterministic],
        contextual=overrides[contextual],
        external=overrides[external],
    )
    with console.status("Analyzing the repository", spinner="dots"):
        try:
            result = analysis.run()
        except ProviderExecutionError as error:
            _fail_provider(error)
        report = CheckReport.of(root, result)
    fixed = _apply_repairs(root, analysis, report, repair, maximum_fixes)
    report = fixed.report
    if output is not None:
        output.write_text(
            report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    if format is CheckFormat.RICH:
        console.print(RichCheck(limit=limit).render(report))
    else:
        console.print(
            format.check(limit).render(report),
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
    _present_repairs(root, fixed, repair, maximum_fixes)
    incomplete = rule_coverage is RuleCoverage.ALL and report.skipped_rule_count
    if (report.failure_count or incomplete) and not report_only:
        raise SystemExit(1)


def _fail_provider(error: ProviderExecutionError) -> Never:
    """Present one external provider boundary failure and leave without a traceback."""
    console.print(str(error), style="red")
    raise SystemExit(2) from None


def _apply_repairs(
    root: Path,
    analysis: Judgment,
    report: CheckReport,
    repair: RepairMode,
    maximum_fixes: int,
) -> FixResult:
    """Apply the explicitly selected safety class through a verified fixpoint."""
    if repair not in {RepairMode.APPLY, RepairMode.APPLY_REVIEW}:
        return FixResult(report=report)
    safety = FixSafety.REVIEW if repair is RepairMode.APPLY_REVIEW else FixSafety.SAFE
    with console.status(f"Applying and verifying {safety} fixes", spinner="dots"):
        return FixSession(
            root,
            analysis,
            safety=safety,
            maximum_fixes=maximum_fixes,
        ).run(report)


def _present_repairs(
    root: Path,
    fixed: FixResult,
    repair: RepairMode,
    maximum_fixes: int,
) -> None:
    """Show applied plans beside every remaining review or rendering refusal."""
    if repair is RepairMode.NONE:
        return
    preview_safety = None if repair is RepairMode.PREVIEW else FixSafety.REVIEW
    previewed, preview_refusals = PythonFixRenderer(root).available(
        fixed.report,
        preview_safety,
        maximum=maximum_fixes,
    )
    refused = list(fixed.refused)
    refused.extend(item for item in preview_refusals if item not in refused)
    FixPresentation(console).show(
        applied=fixed.applied,
        previewed=previewed,
        refused=refused,
    )


def judgment(
    root: Path,
    *,
    select: str,
    suffixes: str,
    kernel: Path | None,
    failure_limit: int | None = None,
    deterministic: ExecutionOverride = ExecutionOverride.UNCHANGED,
    contextual: ExecutionOverride = ExecutionOverride.UNCHANGED,
    external: ExecutionOverride = ExecutionOverride.UNCHANGED,
) -> Judgment:
    """Build the one pass of the engine that every command judging a repository runs."""
    configuration = MCMRConfiguration.read(root)
    configuration = configuration.with_execution(
        deterministic=deterministic,
        contextual=contextual,
        external=external,
    )
    return Judgment(
        binary=kernel or locate(root),
        root=root,
        policies=configuration.policies(),
        select=select,
        suffixes=listed(suffixes) or configuration.scan.suffixes,
        failure_limit=failure_limit,
        configuration=configuration,
    )


def allowance(policies: RulePolicies, definition: RuleDefinition) -> str:
    """Render what the effective policy allows for one rule."""
    return allowed(
        policies.policy(
            rule_id=definition.id,
            candidate=definition.policy,
        )
    )


def listed(value: str) -> list[str]:
    """Return the nonempty items in one comma-separated command value."""
    return [item.strip() for item in value.split(",") if item.strip()]
