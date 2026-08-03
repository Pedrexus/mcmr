from functools import cached_property

from patos import FrozenModel

from .....domain.contracts import FixSafety
from ..rendering import RenderedDirectory, RenderedFile
from .signature import FixSignature


class RenderedFix(FrozenModel):
    """Hold one verified rendering and the finding it intends to close."""

    rule: str
    callable: str
    message: str
    summary: str
    safety: FixSafety
    files: list[RenderedFile]
    directories: list[RenderedDirectory] = []

    @property
    def diff(self) -> str:
        """Return every changed file as one reviewable patch."""
        return "".join(
            [
                *(file.diff for file in self.files),
                *(directory.diff for directory in self.directories),
            ]
        )

    @cached_property
    def signature(self) -> FixSignature:
        """Return a stable identity used to collapse a plan attached to several findings."""
        return FixSignature.model_validate(self, from_attributes=True)
