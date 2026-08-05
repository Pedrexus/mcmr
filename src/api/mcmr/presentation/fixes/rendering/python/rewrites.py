from functools import singledispatchmethod
from typing import TYPE_CHECKING

from .....domain.contracts import (
    Inline,
    Move,
    Placement,
    Remove,
    Rename,
    Replace,
    SourceRewrite,
    Unwrap,
)
from .....domain.errors import UnrenderableFix
from .....facts import MemberKind
from ...contracts import ByteEdit

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .....facts.foundation import NodeRef
    from ..documents import SourceDocument


class PythonRewriteRenderer:
    """Render structural Python operations against their retained documents."""

    def __init__(self, documents: Mapping[str, SourceDocument]) -> None:
        self.documents = documents

    @singledispatchmethod
    def dispatch(self, rewrite: SourceRewrite) -> list[ByteEdit]:
        """Dispatch one structural operation by its typed rewrite model."""
        raise TypeError(f"unsupported rewrite {type(rewrite).__name__}")

    @dispatch.register
    def inline(self, rewrite: Inline) -> list[ByteEdit]:
        """Replace every reference with an exact body before removing its declaration."""
        document = self.documents[rewrite.body.span.path]
        body_start, body_end = document.node_range(rewrite.body)
        source = document.original[body_start:body_end].decode("utf-8")
        return [
            *(
                self._replace_node(node, source, self.documents[node.span.path])
                for node in rewrite.references
            ),
            self._remove(rewrite.declaration),
        ]

    @dispatch.register
    def move(self, rewrite: Move) -> list[ByteEdit]:
        """Move a whole-line node beside an anchor and adapt its indentation."""
        source = self.documents[rewrite.target.span.path]
        destination = self.documents[rewrite.anchor.span.path]
        insertion = self._insertion_offset(destination, rewrite.anchor, rewrite.placement)
        shifted = self._shifted_source(
            source,
            rewrite.target,
            destination=destination,
            anchor=rewrite.anchor,
            prefix=rewrite.prefix,
        )
        removal_start, removal_end = source.deletion_range(rewrite.target)
        return [
            self._edit(
                destination,
                start=insertion,
                end=insertion,
                replacement=shifted,
            ),
            self._edit(source, start=removal_start, end=removal_end, replacement=b""),
        ]

    @dispatch.register
    def remove(self, rewrite: Remove) -> list[ByteEdit]:
        """Remove one exact node and its owned line ending."""
        return [self._remove(rewrite.target)]

    @dispatch.register
    def rename(self, rewrite: Rename) -> list[ByteEdit]:
        """Rename a declaration and every reference only when the set is complete."""
        if not rewrite.symbol.are_references_complete:
            raise UnrenderableFix(f"references for {rewrite.symbol.id} are incomplete")
        if not rewrite.name.isidentifier():
            raise UnrenderableFix(f"{rewrite.name!r} is not an identifier")
        return [
            self._replace_node(node, rewrite.name, self.documents[node.span.path])
            for node in (rewrite.symbol.declaration, *rewrite.symbol.references)
        ]

    @dispatch.register
    def replace(self, rewrite: Replace) -> list[ByteEdit]:
        """Replace one exact retained node with encoded source."""
        document = self.documents[rewrite.target.span.path]
        return [self._replace_node(rewrite.target, rewrite.source, document)]

    @dispatch.register
    def unwrap(self, rewrite: Unwrap) -> list[ByteEdit]:
        """Replace a parent node with one proven descendant's exact source."""
        target, keep = rewrite.target, rewrite.keep
        if target.span.path != keep.span.path:
            raise UnrenderableFix("an unwrap target and descendant must share one file")
        document = self.documents[target.span.path]
        start, end = document.node_range(target)
        keep_start, keep_end = document.node_range(keep)
        if keep_start < start or keep_end > end:
            raise UnrenderableFix(f"{keep.id} is not inside {target.id}")
        return [
            self._edit(
                document,
                start=start,
                end=end,
                replacement=document.original[keep_start:keep_end],
            )
        ]

    @staticmethod
    def _edit(
        document: SourceDocument,
        *,
        start: int,
        end: int,
        replacement: bytes,
    ) -> ByteEdit:
        """Build one byte edit for a known source document."""
        return ByteEdit(
            path=document.path,
            start=start,
            end=end,
            replacement=replacement,
        )

    @staticmethod
    def _insertion_offset(
        document: SourceDocument,
        anchor: NodeRef,
        placement: Placement,
    ) -> int:
        """Return the line boundary one move placement names."""
        anchor_start, anchor_end = document.node_range(anchor)
        if placement is Placement.BEFORE:
            return document.line_bounds(anchor_start)[0]
        return document.line_bounds(anchor_end)[2]

    @staticmethod
    def _line_endings(target: NodeRef, *, anchor: NodeRef) -> int:
        """Separate moved callable members while keeping compact nodes adjacent."""
        separated = {
            MemberKind.CONSTRUCTOR,
            MemberKind.DESTRUCTOR,
            MemberKind.PROPERTY,
            MemberKind.STATIC_METHOD,
            MemberKind.CLASS_METHOD,
            MemberKind.METHOD,
        }
        return 2 if target.kind in separated or anchor.kind in separated else 1

    @staticmethod
    def _relocated(line: bytes, *, target_indent: bytes, anchor_indent: bytes) -> bytes:
        """Return one moved line under its destination indentation, keeping a blank line empty."""
        if not line.strip():
            return line
        body = line[len(target_indent) :] if line.startswith(target_indent) else line
        return anchor_indent + body

    @staticmethod
    def _shifted_source(
        source: SourceDocument,
        target: NodeRef,
        *,
        destination: SourceDocument,
        anchor: NodeRef,
        prefix: str,
    ) -> bytes:
        """Return one node reindented to match its destination anchor."""
        start, end = source.node_range(target)
        anchor_start, _ = destination.node_range(anchor)
        target_indent = source.indentation(start)
        anchor_indent = destination.indentation(anchor_start)
        raw = target_indent + prefix.encode("utf-8") + source.original[start:end]
        shifted = b"".join(
            PythonRewriteRenderer._relocated(
                line, target_indent=target_indent, anchor_indent=anchor_indent
            )
            for line in raw.splitlines(keepends=True)
        )
        crosses_modules = (
            source.path != destination.path and not target_indent and not anchor_indent
        )
        if crosses_modules:
            return destination.newline + shifted + destination.newline
        return shifted + destination.newline * PythonRewriteRenderer._line_endings(
            target,
            anchor=anchor,
        )

    @classmethod
    def _replace_node(
        cls,
        node: NodeRef,
        source: str,
        document: SourceDocument,
    ) -> ByteEdit:
        """Replace one exact node after proving its retained text matches."""
        start, end = document.node_range(node)
        return cls._edit(
            document,
            start=start,
            end=end,
            replacement=source.encode("utf-8"),
        )

    def _remove(self, node: NodeRef) -> ByteEdit:
        """Remove one node through the document named by its span."""
        document = self.documents[node.span.path]
        start, end = document.deletion_range(node)
        return self._edit(document, start=start, end=end, replacement=b"")
