from patos import FrozenModel

from ..rendering import RenderedDirectory, RenderedFile


class FixSignature(FrozenModel):
    """The exact rule, summary, paths, and bytes that make two rendered fixes equivalent."""

    rule: str
    summary: str
    files: list[RenderedFile]
    directories: list[RenderedDirectory] = []
