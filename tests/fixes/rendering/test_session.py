import os
import sys
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import (
    Edit,
    Finding,
    FixPlan,
    FixSafety,
    Remove,
    RemoveDirectory,
    Replace,
)
from mcmr.domain.errors import UnrenderableFix
from mcmr.facts import SourceSpan
from mcmr.presentation import FixSession, PythonFixRenderer, RenderedFix
from mcmr.presentation.fixes import (
    AtomicFixWriter,
    RenderedDirectory,
    RenderedFile,
)
from mcmr.presentation.reports import CheckReport

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from mcmr.commands.quality import Judgment
from .test_operations import failure, node


def rendered_files(*files: RenderedFile) -> RenderedFix:
    """Build one rendered plan for atomic writer tests."""
    return RenderedFix(
        rule="PY-DEMO0001",
        callable="demo",
        message="message",
        summary="summary",
        safety=FixSafety.SAFE,
        files=files,
    )


def test_review_safety_survives_rendering(tmp_path: Path) -> None:
    """Rendering never promotes a review-only plan to an unattended edit."""
    (tmp_path / "sample.py").write_text("import os\n")
    imported = node("sample.py", text="import os", start_line=1, start_column=0, kind="import")
    edit = Edit(
        plan=FixPlan(summary="Remove the import.", rewrites=[Remove(target=imported)]),
        safety=FixSafety.REVIEW,
    )

    fixed = PythonFixRenderer(tmp_path).render(failure(), edit, "unused import")

    assert fixed.safety is FixSafety.REVIEW


@pytest.mark.parametrize("failure_mode", ["verification", "rendering"])
def test_fix_session_bisects_a_batch_that_cannot_verify_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    """A failed large batch retries a useful half without blocking untouched plans."""
    initial = CheckReport(root=str(tmp_path))
    first = rendered_files(RenderedFile(path="a.py", original=b"a", revised=b"b"))
    second = rendered_files(RenderedFile(path="c.py", original=b"c", revised=b"d"))
    session = FixSession(tmp_path, unchanged_judgment())

    def verified(
        current: CheckReport,
        candidates: Sequence[RenderedFix],
    ) -> CheckReport | None:
        """Reject only the pair and accept the first half on its own."""
        assert current is initial
        if len(candidates) == 1:
            return initial
        if failure_mode == "rendering":
            raise UnrenderableFix("overlap")
        return None

    monkeypatch.setattr(session, "_verified", verified)

    current, retained, refused = session.retain(initial, [first, second])

    assert current is initial
    assert retained == [first]
    assert not refused


def test_atomic_writer_applies_restores_and_refuses_stale_source(tmp_path: Path) -> None:
    """Every write is checked against both sides of the snapshot it changes."""
    (target := tmp_path / "sample.py").write_bytes(b"value = 1\n")
    fix = rendered_files(
        RenderedFile(path="sample.py", original=b"value = 1\n", revised=b"value = 2\n")
    )
    writer = AtomicFixWriter(tmp_path)

    assert (writer.apply_changes(fix.files, directories=[]), target.read_bytes()) == (
        None,
        b"value = 2\n",
    )
    assert (writer.restore_changes(fix.files, directories=[]), target.read_bytes()) == (
        None,
        b"value = 1\n",
    )

    target.write_bytes(b"value = 3\n")
    with pytest.raises(UnrenderableFix, match="changed after"):
        writer.apply_changes(fix.files, directories=[])
    with pytest.raises(UnrenderableFix, match="changed while"):
        writer.restore_changes(fix.files, directories=[])


def test_empty_directory_fix_renders_applies_and_restores(tmp_path: Path) -> None:
    """Directory cleanup uses guarded `rmdir` semantics and a reversible snapshot."""
    (target := tmp_path / "unused").mkdir()
    edit = Edit(
        plan=FixPlan(
            summary="Remove the empty directory.",
            rewrites=[RemoveDirectory(target=SourceSpan(path="unused"))],
        )
    )
    fixed = PythonFixRenderer(tmp_path).render(failure(), edit, "unused directory")
    writer = AtomicFixWriter(tmp_path)

    assert fixed.directories == [RenderedDirectory(path="unused")]
    assert fixed.directories[0].diff == "remove empty directory unused/\n"
    writer.apply_changes(fixed.files, directories=fixed.directories)
    assert not target.exists()
    writer.restore_changes(fixed.files, directories=fixed.directories)
    assert target.is_dir()


def test_directory_transaction_refuses_missing_and_nonempty_targets(tmp_path: Path) -> None:
    """Writing rechecks the exact directory state it consumes."""
    directory = RenderedDirectory(path="unused")
    writer = AtomicFixWriter(tmp_path)

    with pytest.raises(UnrenderableFix, match="not a removable directory"):
        writer.apply_changes([], directories=[directory])

    (target := tmp_path / "unused").mkdir()
    (target / "new.txt").write_text("new")
    with pytest.raises(UnrenderableFix, match="no longer empty"):
        writer.apply_changes([], directories=[directory])


def test_directory_transaction_refuses_a_recreated_target(tmp_path: Path) -> None:
    """Restoring a removed directory cannot overwrite a replacement."""
    directory = RenderedDirectory(path="unused")
    writer = AtomicFixWriter(tmp_path)
    (target := tmp_path / "unused").mkdir()
    writer.apply_changes([], directories=[directory])
    target.mkdir()
    with pytest.raises(UnrenderableFix, match="changed while"):
        writer.restore_changes([], directories=[directory])


def test_directory_renderer_refuses_missing_and_nonempty_targets(tmp_path: Path) -> None:
    """A path-only rewrite needs one existing empty physical directory."""
    edit = Edit(
        plan=FixPlan(
            summary="Remove the empty directory.",
            rewrites=[RemoveDirectory(target=SourceSpan(path="unused"))],
        )
    )
    with pytest.raises(UnrenderableFix, match="not a removable directory"):
        PythonFixRenderer(tmp_path).render(failure(), edit, "unused directory")

    (target := tmp_path / "unused").mkdir()
    (target / "new.txt").write_text("new")
    with pytest.raises(UnrenderableFix, match="no longer empty"):
        PythonFixRenderer(tmp_path).render(failure(), edit, "unused directory")


def test_directory_renderer_refuses_symbolic_targets(tmp_path: Path) -> None:
    """A path-only rewrite never follows a symbolic link."""
    edit = Edit(
        plan=FixPlan(
            summary="Remove the empty directory.",
            rewrites=[RemoveDirectory(target=SourceSpan(path="unused"))],
        )
    )
    (held := tmp_path / "held").mkdir()
    (tmp_path / "unused").symlink_to(held, target_is_directory=True)
    with pytest.raises(UnrenderableFix, match="not a removable directory"):
        PythonFixRenderer(tmp_path).render(failure(), edit, "unused directory")


def test_atomic_writer_rolls_back_files_written_before_an_os_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later replacement failure restores every earlier file in the same plan."""
    (tmp_path / "a.py").write_bytes(b"a = 1\n")
    (tmp_path / "b.py").write_bytes(b"b = 1\n")
    fix = rendered_files(
        RenderedFile(path="a.py", original=b"a = 1\n", revised=b"a = 2\n"),
        RenderedFile(path="b.py", original=b"b = 1\n", revised=b"b = 2\n"),
    )
    writer = AtomicFixWriter(tmp_path)
    replace = os.replace

    def fail_on_second(source: str, target: os.PathLike[str]) -> None:
        """Fail only the attempted new version of the second file."""
        if os.fspath(target).endswith("/b.py"):
            raise OSError("disk refused the write")
        replace(source, target)

    monkeypatch.setattr(os, "replace", fail_on_second)

    with pytest.raises(OSError, match="disk refused"):
        writer.apply_changes(fix.files, directories=fix.directories)
    assert (
        (tmp_path / "a.py").read_bytes(),
        (tmp_path / "b.py").read_bytes(),
    ) == (b"a = 1\n", b"b = 1\n")


class UnchangedJudgment:
    """Return a token a patched report builder maps back to the unchanged report."""

    def model_copy(self, *, update: Mapping[str, str | None]) -> UnchangedJudgment:
        """Accept the same narrowing API a real judgment exposes."""
        return self

    def run(self) -> int:
        """Return the token standing in for a rerun."""
        return 1


def unchanged_judgment() -> Judgment:
    """Adapt the deliberately small test double to the concrete session boundary."""
    return cast("Judgment", UnchangedJudgment())


def test_fix_session_verifies_compatible_plans_in_one_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independent exact edits share one fresh analysis and one atomic source snapshot."""
    (module := tmp_path / "sample.py").write_text("value = 1\n")
    name = node("sample.py", text="value", start_line=1, start_column=0)
    number = node("sample.py", text="1", start_line=1, start_column=8)
    findings = (
        Finding(
            message="rename value",
            span=name.span,
            repair=Edit(
                plan=FixPlan(
                    summary="Rename value.",
                    rewrites=[Replace(target=name, source="held")],
                )
            ),
        ),
        Finding(
            message="replace number",
            span=number.span,
            repair=Edit(
                plan=FixPlan(
                    summary="Replace number.",
                    rewrites=[Replace(target=number, source="2")],
                )
            ),
        ),
    )
    initial = CheckReport(
        root=str(tmp_path),
        failures=(failure().model_copy(update={"findings": findings}),),
    )
    resolved = CheckReport(root=str(tmp_path))

    class ResolvedReportBuilder:
        """Count and resolve the one verification run made for the whole batch."""

        calls = 0

        @classmethod
        def of(cls, root: Path, judged: int) -> CheckReport:
            """Return a report proving both distinct finding messages closed."""
            assert root == tmp_path
            assert judged == 1
            cls.calls += 1
            return resolved

    monkeypatch.setattr(sys.modules[FixSession.__module__], "CheckReport", ResolvedReportBuilder)

    result = FixSession(tmp_path, unchanged_judgment()).run(initial)

    assert (
        len(result.applied),
        result.refused,
        module.read_text(),
        ResolvedReportBuilder.calls,
    ) == (2, [], "held = 2\n", 1)


def test_fix_session_restores_an_edit_whose_finding_remains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful parsing is insufficient when the originating rule still objects."""
    (module := tmp_path / "sample.py").write_text("value = 1\n")
    target = node("sample.py", text="value", start_line=1, start_column=0)
    edit = Edit(
        plan=FixPlan(summary="Rename value.", rewrites=[Replace(target=target, source="held")])
    )
    found = Finding(message="sample needs repair", span=target.span, repair=edit)
    initial = CheckReport(
        root=str(tmp_path),
        failures=(failure().model_copy(update={"findings": (found,)}),),
    )

    class UnchangedReportBuilder:
        """Map every rerun token back to one deliberately unchanged report."""

        def __init__(self, root: Path, report: CheckReport) -> None:
            self.root = root
            self.report = report

        def of(self, root: Path, judged: int) -> CheckReport:
            """Return the retained report after validating the fake rerun boundary."""
            assert root == self.root
            assert judged == 1
            return self.report

    monkeypatch.setattr(
        sys.modules[FixSession.__module__],
        "CheckReport",
        UnchangedReportBuilder(tmp_path, initial),
    )
    session = FixSession(tmp_path, unchanged_judgment())

    result = session.run(initial)

    assert (
        result.applied,
        result.refused[0].reason.endswith("originating finding remained"),
        module.read_text(),
        FixSession(tmp_path, unchanged_judgment(), maximum_fixes=0).run(initial).report,
    ) == ([], True, "value = 1\n", initial)
