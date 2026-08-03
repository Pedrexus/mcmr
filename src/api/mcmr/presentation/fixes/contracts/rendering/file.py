import difflib

from patos import FrozenModel

from .edit import ByteEdit


class _RenderedPathTypes:
    """Own the closed rendered path changes one atomic fix may carry."""

    class Directory(FrozenModel):
        """Keep one directory proven empty when a fix was rendered."""

        path: str

        @property
        def diff(self) -> str:
            """Describe the directory removal beside source diffs."""
            return f"remove empty directory {self.path}/\n"

    class File(FrozenModel):
        """Keep one file before and after an atomic fix."""

        path: str
        original: bytes
        revised: bytes
        edits: list[ByteEdit] = []

        @property
        def diff(self) -> str:
            """Return the unified diff a reader reviews before source is changed."""
            before = self.original.decode("utf-8").splitlines(keepends=True)
            after = self.revised.decode("utf-8").splitlines(keepends=True)
            return "".join(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{self.path}",
                    tofile=f"b/{self.path}",
                )
            )


RenderedDirectory = _RenderedPathTypes.Directory
RenderedFile = _RenderedPathTypes.File
