import os
import stat
import tempfile
from contextlib import suppress
from typing import TYPE_CHECKING

from ....domain.errors import UnrenderableFix

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from ..contracts import RenderedDirectory, RenderedFile


class AtomicFixWriter:
    """Replace every changed file through a sibling temporary and retain rollback bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def apply_changes(
        self,
        files: Sequence[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory],
    ) -> None:
        """Apply file replacements and guarded empty-directory removals atomically."""
        for file in files:
            current = (self.root / file.path).read_bytes()
            if current != file.original:
                raise UnrenderableFix(f"{file.path} changed after its fix was rendered")
        self._require_empty(directories)
        written: list[RenderedFile] = []
        removed: list[RenderedDirectory] = []
        try:
            self._commit(files, written, directories=directories, removed=removed)
        except OSError as failure:
            raise self._rollback(failure, written, directories=removed) from None

    def restore_changes(
        self,
        files: Sequence[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory],
    ) -> None:
        """Restore revised files and recreate every directory the batch removed."""
        for file in files:
            current = (self.root / file.path).read_bytes()
            if current != file.revised:
                raise UnrenderableFix(f"{file.path} changed while its fix was being verified")
        for directory in directories:
            if (self.root / directory.path).exists():
                raise UnrenderableFix(f"{directory.path} changed while its fix was being verified")
        self._restore_directories(directories)
        for file in files:
            self._replace(file.path, file.original)

    @staticmethod
    def _discard_temporary(temporary: str) -> None:
        """Remove a leftover temporary when replacement did not consume it."""
        with suppress(FileNotFoundError):
            os.unlink(temporary)

    @staticmethod
    def _write_temporary(
        descriptor: int,
        temporary: str,
        target: Path,
        content: bytes,
        mode: int,
    ) -> None:
        """Flush one sibling temporary before atomically replacing its destination."""
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)

    def _commit(
        self,
        files: Sequence[RenderedFile],
        written: list[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory],
        removed: list[RenderedDirectory],
    ) -> None:
        """Perform the fallible write phase whose caller owns rollback."""
        self._write(files, written)
        self._remove_directories(directories, removed)

    def _remove_directories(
        self,
        directories: Sequence[RenderedDirectory],
        removed: list[RenderedDirectory],
    ) -> None:
        """Remove each still-empty directory and retain rollback order."""
        for directory in directories:
            (self.root / directory.path).rmdir()
            removed.append(directory)

    def _replace(self, relative: str, content: bytes) -> None:
        """Atomically replace one file while preserving its permission bits."""
        target = self.root / relative
        mode = stat.S_IMODE(target.stat().st_mode)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            self._write_temporary(descriptor, temporary, target, content, mode)
        finally:
            self._discard_temporary(temporary)

    def _require_empty(self, directories: Sequence[RenderedDirectory]) -> None:
        """Refuse a directory target that disappeared, changed kind, or gained content."""
        for directory in directories:
            target = self.root / directory.path
            if target.is_symlink() or not target.is_dir():
                raise UnrenderableFix(f"{directory.path} is not a removable directory")
            if next(target.iterdir(), None) is not None:
                raise UnrenderableFix(f"{directory.path} is no longer empty")

    def _restore_directories(self, directories: Sequence[RenderedDirectory]) -> None:
        """Recreate removed directories from shallowest to deepest."""
        for directory in reversed(directories):
            (self.root / directory.path).mkdir()

    def _restore_originals(
        self,
        files: Sequence[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory] = (),
    ) -> None:
        """Restore revised files in reverse write order after a failed transaction."""
        self._restore_directories(directories)
        for file in reversed(files):
            self._replace(file.path, file.original)

    def _rollback(
        self,
        failure: OSError,
        files: Sequence[RenderedFile],
        *,
        directories: Sequence[RenderedDirectory] = (),
    ) -> OSError:
        """Restore a failed transaction and preserve its write failure."""
        self._restore_originals(files, directories=directories)
        return failure

    def _write(self, files: Sequence[RenderedFile], written: list[RenderedFile]) -> None:
        """Write each revised file and record enough state for transactional rollback."""
        for file in files:
            self._replace(file.path, file.revised)
            written.append(file)
