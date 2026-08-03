from pathlib import Path
from typing import TYPE_CHECKING

from .....domain.contracts import Edit, Finding, ImportRequest, Move, RemoveDirectory, Replace
from .....domain.errors import UnrenderableFix
from ...contracts import ByteEdit, FixRefusal, RenderedDirectory, RenderedFile, RenderedFix
from ..documents import SourceDocument
from ..edits import EditNormalizer
from .imports import PythonImportRenderer, parse_python
from .rewrites import PythonRewriteRenderer

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping, Sequence

    from .....domain.contracts import FixSafety, SourceRewrite
    from ....reports import CheckReport, RuleFailure


class PythonFixRenderer:
    """Render typed Python rewrites into validated, conflict-free UTF-8 byte edits."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def merge_directories(fixes: Sequence[RenderedFix]) -> list[RenderedDirectory]:
        """Return each exact directory removal once in deepest-first order."""
        found = {directory.path: directory for fix in fixes for directory in fix.directories}
        return sorted(found.values(), key=lambda item: (-item.path.count("/"), item.path))

    def available(
        self,
        report: CheckReport,
        safety: FixSafety | None = None,
        *,
        maximum: int | None = None,
    ) -> tuple[list[RenderedFix], list[FixRefusal]]:
        """Render unique eligible plans and retain a reason for every refusal."""
        self._validate_maximum(maximum)
        if maximum == 0:
            return [], []
        refused: list[FixRefusal] = []
        fixes = self._available_fixes(report, safety, maximum, refused)
        return fixes, refused

    def merge(self, fixes: Sequence[RenderedFix]) -> list[RenderedFile]:
        """Compose independently rendered plans over their shared source snapshots."""
        grouped: dict[str, list[RenderedFile]] = {}
        for fix in fixes:
            for file in fix.files:
                grouped.setdefault(file.path, []).append(file)
        return [self._merge_file(path, grouped[path]) for path in sorted(grouped)]

    def render(self, failure: RuleFailure, edit: Edit, message: str) -> RenderedFix:
        """Render one atomic plan and refuse stale, overlapping, or invalid source."""
        files = self._rendered_files(edit)
        directories = self._rendered_directories(edit)
        self._require_change(files, directories=directories)
        return self._rendered_fix(failure, edit, message, files, directories=directories)

    @staticmethod
    def _apply_edits(document: SourceDocument, edits: Sequence[ByteEdit]) -> bytes:
        """Apply ordered byte edits from right to left."""
        revised = document.original
        for edit in reversed(edits):
            revised = revised[: edit.start] + edit.replacement + revised[edit.end :]
        return revised

    @staticmethod
    def _eligible_edit(finding: Finding, safety: FixSafety | None) -> Edit | None:
        """Return an edit when one finding matches the requested safety."""
        if not isinstance(finding.repair, Edit):
            return None
        if safety is not None and finding.repair.safety is not safety:
            return None
        return finding.repair

    @staticmethod
    def _merge_edits(
        document: SourceDocument,
        files: Sequence[RenderedFile],
    ) -> list[ByteEdit]:
        """Return normalized edits from current nonempty source snapshots."""
        PythonFixRenderer._require_current(document, files)
        if any(not file.edits for file in files):
            raise UnrenderableFix(f"{document.path} has no exact edits to merge")
        return EditNormalizer([edit for file in files for edit in file.edits]).normalize()

    @staticmethod
    def _record_refusal(
        refused: list[FixRefusal],
        *,
        rule: str,
        summary: str,
        reason: str,
    ) -> None:
        """Retain one unique rendering refusal for the final fix ledger."""
        refusal = FixRefusal(rule=rule, summary=summary, reason=reason)
        if refusal not in refused:
            refused.append(refusal)

    @staticmethod
    def _remember_imports(
        rewrite: SourceRewrite,
        requested: MutableMapping[str, list[ImportRequest]],
    ) -> None:
        """Retain imports attached to one rewrite at its destination."""
        if isinstance(rewrite, Replace):
            requested.setdefault(rewrite.target.span.path, []).extend(rewrite.imports)
        elif isinstance(rewrite, Move) and rewrite.imports:
            requested.setdefault(rewrite.anchor.span.path, []).extend(rewrite.imports)

    @staticmethod
    def _render_imports(
        documents: Mapping[str, SourceDocument],
        *,
        requested: Mapping[str, Sequence[ImportRequest]],
        rendered: list[ByteEdit],
    ) -> None:
        """Append one import insertion for every document that needs one."""
        for path, requirements in requested.items():
            rendered.extend(PythonImportRenderer(documents[path], requirements).render())

    @staticmethod
    def _rendered_fix(
        failure: RuleFailure,
        edit: Edit,
        message: str,
        files: list[RenderedFile],
        *,
        directories: list[RenderedDirectory],
    ) -> RenderedFix:
        """Build one rendered fix from its validated files."""
        return RenderedFix(
            rule=failure.rule,
            callable=failure.callable,
            message=message,
            summary=edit.summary,
            safety=edit.safety,
            files=files,
            directories=directories,
        )

    @staticmethod
    def _require_change(
        files: Sequence[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory],
    ) -> None:
        """Refuse a plan whose complete byte program changes no source."""
        if not directories and not any(file.original != file.revised for file in files):
            raise UnrenderableFix("the fix plan would not change source")

    @staticmethod
    def _require_current(
        document: SourceDocument,
        files: Sequence[RenderedFile],
    ) -> None:
        """Require every rendered file to share the current source snapshot."""
        if any(file.original != document.original for file in files):
            raise UnrenderableFix(f"{document.path} changed after its fix was rendered")

    @staticmethod
    def _revised(document: SourceDocument, edits: Sequence[ByteEdit]) -> RenderedFile:
        """Apply one file's edits and parse languages available in this process."""
        revised = PythonFixRenderer._apply_edits(document, edits)
        if Path(document.path).suffix in {".py", ".pyi"}:
            parse_python(revised.decode("utf-8"), path=document.path)
        return RenderedFile(
            path=document.path,
            original=document.original,
            revised=revised,
            edits=list(edits),
        )

    @staticmethod
    def _rewrite_paths(rewrite: SourceRewrite) -> set[str]:
        """Return supported source paths addressed by one rewrite."""
        paths = {span.path for span in rewrite.spans}
        suffixes = {Path(path).suffix for path in paths}
        if not suffixes <= {".py", ".pyi", ".rs"}:
            raise UnrenderableFix("the source renderer only edits Python and Rust source")
        if ".rs" in suffixes and (
            not isinstance(rewrite, Move) or rewrite.prefix or rewrite.imports or len(paths) != 1
        ):
            raise UnrenderableFix("the source renderer only supports exact moves in Rust source")
        return paths

    @staticmethod
    def _validate_maximum(maximum: int | None) -> None:
        """Require a nonnegative optional rendered fix limit."""
        if maximum is not None and maximum < 0:
            raise ValueError("maximum rendered fixes cannot be negative")

    def _append_available(
        self,
        fixes: list[RenderedFix],
        failure: RuleFailure,
        refused: list[FixRefusal],
        finding: Finding,
        safety: FixSafety | None = None,
    ) -> None:
        """Append one rendered finding when its exact edit program is new."""
        rendered = self._render_available(failure, finding, safety, refused)
        if rendered is None or any(rendered.signature == item.signature for item in fixes):
            return
        fixes.append(rendered)

    def _available_fixes(
        self,
        report: CheckReport,
        safety: FixSafety | None,
        maximum: int | None,
        refused: list[FixRefusal],
    ) -> list[RenderedFix]:
        """Render unique findings until the optional limit is reached."""
        fixes: list[RenderedFix] = []
        for failure in report.failures:
            for finding in failure.reported:
                self._append_available(fixes, failure, refused, finding, safety)
                if maximum is not None and len(fixes) == maximum:
                    return fixes
        return fixes

    def _merge_file(self, path: str, files: Sequence[RenderedFile]) -> RenderedFile:
        """Merge exact nonoverlapping edits against one unchanged source document."""
        document = SourceDocument(self.root, path)
        if len(files) == 1:
            self._require_current(document, files)
            return files[0]
        return self._revised(document, self._merge_edits(document, files))

    def _refused(
        self,
        refused: list[FixRefusal],
        failure: RuleFailure,
        edit: Edit,
        error: FileNotFoundError | UnrenderableFix,
    ) -> RenderedFix | None:
        """Retain one rendering failure and return no rendered fix."""
        self._record_refusal(
            refused,
            rule=failure.rule,
            summary=edit.summary,
            reason=str(error),
        )
        return None

    def _render_available(
        self,
        failure: RuleFailure,
        finding: Finding,
        safety: FixSafety | None,
        refused: list[FixRefusal],
    ) -> RenderedFix | None:
        """Render one eligible finding or retain why its plan could not render."""
        edit = self._eligible_edit(finding, safety)
        if edit is None:
            return None
        try:
            return self.render(failure, edit, finding.message)
        except (FileNotFoundError, UnrenderableFix) as error:
            return self._refused(refused, failure, edit, error)

    def _render_files(
        self,
        documents: Mapping[str, SourceDocument],
        *,
        edits: Sequence[ByteEdit],
    ) -> list[RenderedFile]:
        """Apply normalized edits to every addressed document in path order."""
        return [
            self._revised(document, [item for item in edits if item.path == path])
            for path, document in sorted(documents.items())
        ]

    def _render_rewrites(
        self,
        edit: Edit,
        *,
        documents: MutableMapping[str, SourceDocument],
        requested: MutableMapping[str, list[ImportRequest]],
    ) -> list[ByteEdit]:
        """Render every rewrite while collecting its documents and import requests."""
        rendered: list[ByteEdit] = []
        for rewrite in edit.plan.rewrites:
            if isinstance(rewrite, RemoveDirectory):
                continue
            for path in self._rewrite_paths(rewrite):
                documents.setdefault(path, SourceDocument(self.root, path))
            rendered.extend(PythonRewriteRenderer(documents).dispatch(rewrite))
            self._remember_imports(rewrite, requested)
        return rendered

    def _rendered_directories(self, edit: Edit) -> list[RenderedDirectory]:
        """Retain directory removals only while each target exists and is empty."""
        rendered: list[RenderedDirectory] = []
        for rewrite in edit.plan.rewrites:
            if not isinstance(rewrite, RemoveDirectory):
                continue
            target = self.root / rewrite.target.path
            if target.is_symlink() or not target.is_dir():
                raise UnrenderableFix(f"{rewrite.target.path} is not a removable directory")
            if next(target.iterdir(), None) is not None:
                raise UnrenderableFix(f"{rewrite.target.path} is no longer empty")
            rendered.append(RenderedDirectory(path=rewrite.target.path))
        return rendered

    def _rendered_files(self, edit: Edit) -> list[RenderedFile]:
        """Render and validate every file in one atomic edit program."""
        documents: dict[str, SourceDocument] = {}
        requested: dict[str, list[ImportRequest]] = {}
        rendered = self._render_rewrites(edit, documents=documents, requested=requested)
        self._render_imports(documents, requested=requested, rendered=rendered)
        files = self._render_files(documents, edits=EditNormalizer(rendered).normalize())
        return files
