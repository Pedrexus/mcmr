from typing import TYPE_CHECKING

from .....domain.errors import UnrenderableFix

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...contracts import ByteEdit


class EditNormalizer:
    """Normalize one byte-edit program before it touches source."""

    def __init__(self, edits: Sequence[ByteEdit]) -> None:
        self.edits = list(edits)

    def normalize(self) -> list[ByteEdit]:
        """Collapse duplicate insertions and reject every overlapping replacement."""
        ordered = sorted(self._combined(), key=lambda item: (item.path, item.start, item.end))
        self._reject_overlaps(ordered)
        return ordered

    @staticmethod
    def _matching_insertion(combined: Sequence[ByteEdit], edit: ByteEdit) -> int | None:
        """Return the insertion already occupying this exact path and offset."""
        if edit.start != edit.end:
            return None
        return next(
            (
                index
                for index, existing in enumerate(combined)
                if existing.path == edit.path
                and existing.start == edit.start
                and existing.end == edit.end
            ),
            None,
        )

    @staticmethod
    def _overlap(previous: ByteEdit, *, edit: ByteEdit) -> bool:
        """Whether two ordered edits claim incompatible byte ranges."""
        overlaps = previous.end > edit.start and previous.start != previous.end
        inserts_inside = edit.start == edit.end and previous.start < edit.start < previous.end
        return overlaps or inserts_inside

    def _combined(self) -> list[ByteEdit]:
        """Merge insertions that share one byte offset."""
        combined: list[ByteEdit] = []
        for edit in self._unique():
            matching = self._matching_insertion(combined, edit)
            if matching is None:
                combined.append(edit)
                continue
            held = combined[matching]
            combined[matching] = held.model_copy(
                update={"replacement": held.replacement + edit.replacement}
            )
        return combined

    def _reject_overlaps(self, ordered: Sequence[ByteEdit]) -> None:
        """Reject sorted edits whose byte ranges cannot be applied atomically."""
        previous: ByteEdit | None = None
        for edit in ordered:
            if (
                previous is not None
                and previous.path == edit.path
                and self._overlap(previous, edit=edit)
            ):
                raise UnrenderableFix(
                    f"fix edits overlap in {edit.path} at bytes {previous.start} and {edit.start}"
                )
            previous = edit

    def _unique(self) -> list[ByteEdit]:
        """Validate every range and retain each exact edit once."""
        unique: list[ByteEdit] = []
        for edit in self.edits:
            if edit.start > edit.end:
                raise UnrenderableFix(f"edit in {edit.path} ends before it starts")
            if edit not in unique:
                unique.append(edit)
        return unique
