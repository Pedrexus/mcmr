import re
from pathlib import Path
from shutil import copytree
from tempfile import mkdtemp
from time import perf_counter
from typing import TYPE_CHECKING

import anyio

from ...execution.providers import ExternalEvidence, PublicationContext
from ...presentation import CheckReport
from ...presentation.reports import CheckFormat
from ...project import ExecutionOverride
from ..interface import RepairMode, app, console
from .checking import check, judgment

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from pydantic import JsonValue

# The canonical DataHub dataset URN, the one exact identity a finding message carries.
_SUBJECT = re.compile(r"urn:li:dataset:\([^)]*\)")

# The rule the recorded catalog proves a repair for, which is the one the clean rerun answers.
_REPAIRED = "missing_data_field_reference"

# The whole DataHub rule family, selected by the package every one of those rules lives in.
_FAMILY = "data_assets"


@app.command
def demo(example: Path = Path("examples/datahub")) -> None:
    """Run the complete DataHub workflow over a recorded catalog with no running service.

    example: the recorded DataHub example, copied into a fresh workspace before anything is edited.
    """
    workspace = Path(mkdtemp(prefix="mcmr-demo-"))
    copytree(example, workspace, dirs_exist_ok=True)
    console.print(f"Workspace {workspace}", style="dim")
    reviewed = _checked(workspace, _FAMILY)
    elapsed = {
        "review": _timed("1. What the catalog says about this change", reviewed),
        "preview": _timed(
            "2. The repair the catalog proves",
            _checked(workspace, _REPAIRED, repair=RepairMode.PREVIEW),
        ),
        "apply": _timed(
            "3. The repair applied and verified by a rerun",
            _checked(workspace, _REPAIRED, repair=RepairMode.APPLY),
        ),
        "rerun": _timed("4. The finding is closed", _checked(workspace, _REPAIRED)),
        "writeback": _timed(
            "5. The result written back for the next agent",
            lambda: writeback(workspace, select=_FAMILY),
        ),
    }
    total = sum(elapsed.values())
    timings = "  ".join(f"{name} {seconds:.2f}s" for name, seconds in elapsed.items())
    console.print(f"\n{timings}  total {total:.2f}s")


def _checked(
    workspace: Path,
    select: str,
    *,
    repair: RepairMode = RepairMode.NONE,
) -> Callable[[], None]:
    """Return one bound check over the recorded catalog, ready for the step that times it."""

    def run() -> None:
        check(
            workspace,
            select=select,
            format=CheckFormat.CONCISE,
            repair=repair,
            external=True,
            report_only=True,
        )

    return run


def _timed(title: str, step: Callable[[], None]) -> float:
    """Run one demonstration step under its heading and return its wall time."""
    console.print(f"\n[bold]{title}[/bold]")
    started = perf_counter()
    step()
    return perf_counter() - started


# The canonical DataHub dataset URN, which is the one exact identity a finding message carries.
_SUBJECT = re.compile(r"urn:li:dataset:\([^)]*\)")


@app.command
def writeback(root: Path = Path(), *, select: str = "", label: str = "MCMR policy run") -> None:
    """Write one completed run back to the systems that supplied its external evidence.

    Nothing else in MCMR publishes. A check reads evidence and never returns any, so a run only
    reaches a catalog when somebody asks for it by name.

    root: repository to analyze and then report on.
    select: substring that narrows the selected rules by callable.
    label: the link label each governed asset receives.
    """
    analysis = judgment(
        root,
        select=select,
        suffixes="",
        kernel=None,
        external=ExecutionOverride.ENABLED,
    )
    with console.status("Analyzing the repository", spinner="dots"):
        report = CheckReport.of(root, analysis.run())
    subjects = _subjects(report)
    if not subjects:
        console.print("No governed asset was named by this run, so nothing was written back.")
        return
    receipts = anyio.run(_publish, root, subjects, label, analysis.configuration.providers)
    for receipt in receipts:
        console.print(f"wrote back {receipt}")
    console.print(f"{len(receipts)} of {len(subjects)} governed assets carry this run.")


def _subjects(report: CheckReport) -> list[str]:
    """Return every governed asset the run named, in first-reported order."""
    messages = [finding.message for failure in report.failures for finding in failure.reported]
    named = [match for message in messages for match in _SUBJECT.findall(message)]
    return list(dict.fromkeys(named))


async def _publish(
    root: Path,
    subjects: list[str],
    label: str,
    settings: Mapping[str, dict[str, JsonValue]],
) -> list[str]:
    """Hand the named assets to every installed provider that can publish a result."""
    evidence = ExternalEvidence.for_repository(root, settings)
    receipts: list[str] = []
    for name, publisher in evidence.publishers.items():
        receipts.extend(
            await publisher.publish(
                PublicationContext(
                    repository=root,
                    settings=settings.get(name, {}),
                    subjects=subjects,
                    label=label,
                )
            )
        )
    return receipts
