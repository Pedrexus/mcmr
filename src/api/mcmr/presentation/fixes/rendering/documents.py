from bisect import bisect_right
from typing import TYPE_CHECKING

from ....domain.errors import UnrenderableFix
from ....facts import MemberKind

if TYPE_CHECKING:
    from pathlib import Path

    from ....facts.foundation import NodeRef, SourceSpan


class SourceDocument:
    """Read one UTF-8 source file through the byte coordinates providers promise."""

    def __init__(self, root: Path, path: str) -> None:
        self.path = path
        self.original = (root / path).read_bytes()
        try:
            self.text = self.original.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UnrenderableFix(f"{path} is not valid UTF-8") from error
        self.line_starts = [0]
        self.line_starts.extend(
            index + 1 for index, byte in enumerate(self.original) if byte == ord("\n")
        )

    @property
    def newline(self) -> bytes:
        """Return the first line ending already used by this document."""
        for line in self.original.splitlines(keepends=True):
            ending = line[len(line.rstrip(b"\r\n")) :]
            if ending:
                return ending
        return b"\n"

    def deletion_range(self, node: NodeRef) -> tuple[int, int]:
        """Include a line ending when a node is the line's only meaningful source."""
        start, end = self.node_range(node)
        if node.kind == "sequence-item":
            return self._sequence_item_range(start, end=end)
        line_start, _, _ = self.line_bounds(start)
        _, content_end, line_end = self.line_bounds(end)
        if self.original[line_start:start].strip() or self.original[end:content_end].strip():
            return start, end
        separated = node.kind in {
            MemberKind.CONSTRUCTOR,
            MemberKind.DESTRUCTOR,
            MemberKind.PROPERTY,
            MemberKind.STATIC_METHOD,
            MemberKind.CLASS_METHOD,
            MemberKind.METHOD,
        }
        if node.kind not in {"comment", "comment-group", "function", "import"} and not separated:
            return line_start, line_end
        line_end = self._following_blank_end(line_end)
        return (
            self._separated_start(line_start=line_start, line_end=line_end)
            if separated
            else (line_start, line_end)
        )

    def indentation(self, offset: int) -> bytes:
        """Return whitespace preceding a node on its opening line."""
        line_start, _, _ = self.line_bounds(offset)
        prefix = self.original[line_start:offset]
        if prefix.strip():
            raise UnrenderableFix(f"{self.path} node does not open after indentation")
        return prefix

    def line_bounds(self, offset: int) -> tuple[int, int, int]:
        """Return the start, content end, and ending-inclusive end of one source line."""
        index = max(bisect_right(self.line_starts, offset) - 1, 0)
        start = self.line_starts[index]
        end = (
            self.line_starts[index + 1]
            if index + 1 < len(self.line_starts)
            else len(self.original)
        )
        content_end = end
        if self.original[max(start, content_end - 2) : content_end] == b"\r\n":
            content_end -= 2
        elif self.original[max(start, content_end - 1) : content_end] == b"\n":
            content_end -= 1
        return start, content_end, end

    def node_range(self, node: NodeRef) -> tuple[int, int]:
        """Return a node range only when its retained text still matches source exactly."""
        if not node.text:
            raise UnrenderableFix(f"{node.id} retains no source text")
        start, end = self.span_range(node.span)
        held = self.original[start:end]
        expected = node.text.encode("utf-8")
        if held != expected:
            raise UnrenderableFix(
                f"{node.id} expected {node.text!r} but its source range holds "
                f"{held.decode('utf-8', errors='replace')!r}"
            )
        return start, end

    def offset(self, line: int, *, column: int) -> int:
        """Convert one-based lines and zero-based byte columns into an absolute byte offset."""
        try:
            start = self.line_starts[line - 1]
        except IndexError as error:
            raise UnrenderableFix(f"{self.path} has no line {line}") from error
        boundary = self.line_starts[line] if line < len(self.line_starts) else len(self.original)
        offset = start + column
        if offset > boundary:
            raise UnrenderableFix(f"{self.path}:{line} has no byte column {column}")
        return offset

    def span_range(self, span: SourceSpan) -> tuple[int, int]:
        """Return the byte range a provider span addresses in this document."""
        if span.path != self.path:
            raise UnrenderableFix(f"span for {span.path} was read against {self.path}")
        return (
            self.offset(span.start_line, column=span.start_column),
            self.offset(span.end_line, column=span.end_column),
        )

    @staticmethod
    def _horizontal_width(source: bytes) -> int:
        """Count leading spaces and tabs without consuming a line ending."""
        return len(source) - len(source.lstrip(b" \t"))

    def _closes_scope(self, line_end: int) -> bool:
        """Return whether the source after an offset closes a brace scope."""
        _, following_content, _ = self.line_bounds(line_end)
        return self.original[line_end:following_content].lstrip().startswith(b"}")

    def _following_blank_end(self, line_end: int) -> int:
        """Return the first offset after the blank lines following a removed node."""
        while line_end < len(self.original):
            _, following_content, following_end = self.line_bounds(line_end)
            if self.original[line_end:following_content].strip():
                break
            line_end = following_end
        return line_end

    def _separated_start(self, *, line_start: int, line_end: int) -> tuple[int, int]:
        """Include the preceding blank before a separated member closing its scope."""
        if not line_start or line_end < len(self.original) and not self._closes_scope(line_end):
            return line_start, line_end
        previous_start, previous_content, _ = self.line_bounds(line_start - 1)
        return (
            (previous_start, line_end)
            if not self.original[previous_start:previous_content].strip()
            else (line_start, line_end)
        )

    def _sequence_item_range(self, start: int, *, end: int) -> tuple[int, int]:
        """Remove one exact sequence item together with one adjacent comma."""
        line_start, content_end, line_end = self.line_bounds(start)
        before = self.original[line_start:start]
        after = self.original[end:content_end]
        if not before.strip() and after.lstrip().startswith(b","):
            trailing = after.lstrip()[1:]
            if not trailing.strip():
                return line_start, line_end
        right = end + self._horizontal_width(self.original[end:])
        if self.original[right : right + 1] == b",":
            right += 1
            right += self._horizontal_width(self.original[right:])
            return start, right
        left = start - (len(self.original[:start]) - len(self.original[:start].rstrip(b" \t")))
        if self.original[left - 1 : left] == b",":
            return left - 1, end
        return start, end
