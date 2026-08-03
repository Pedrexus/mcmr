from functools import cached_property
from typing import TYPE_CHECKING, Self

from pydantic import model_validator

from ...foundation import Fact, SyntaxElement, SyntaxRecord
from .packed import PackedNode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...symbols.syntax.node import SyntaxNode


class SyntaxFact(Fact):
    """Describe one declaration as a tree and its retained source."""

    qualname: str = ""
    kind: str = ""
    source: str = ""
    tree: SyntaxNode | None = None
    nodes: list[SyntaxRecord] = []

    @property
    def root(self) -> SyntaxElement | None:
        """Return the declaration root from expanded or compact records."""
        return self.tree if self.tree is not None else PackedNode(self, 0) if self.nodes else None

    @property
    def span_tuple(self) -> tuple[int, int, int, int]:
        """Return the fact span in compact record order."""
        return (
            self.span.start_line,
            self.span.start_column,
            self.span.end_line,
            self.span.end_column,
        )

    @model_validator(mode="after")
    def carries_one_complete_tree(self) -> Self:
        """Require exactly one complete located declaration tree."""
        if self.tree is not None and self.nodes:
            raise ValueError("a syntax fact cannot carry both expanded and compact trees")
        if self.tree is not None:
            self._validate_expanded_tree(self.tree)
        elif self.nodes:
            self._validate_compact_tree()
        return self

    def text_of(self, node: SyntaxElement) -> str:
        """Return the exact source one node spans within this declaration."""
        if node.text:
            return node.text
        if node.span is None:
            raise ValueError("a syntax node without retained text must carry a source span")
        self._validate_node_path(node)
        start = self._source_offset(node.span.start_line, column=node.span.start_column)
        end = self._source_offset(node.span.end_line, column=node.span.end_column)
        return self._source_bytes[start:end].decode()

    @cached_property
    def _source_bytes(self) -> bytes:
        """Encode retained source once because parser columns are UTF-8 byte offsets."""
        return self.source.encode()

    @cached_property
    def _source_line_offsets(self) -> list[int]:
        """Index retained source lines for constant-time node slicing."""
        return [0, *(at + 1 for at, byte in enumerate(self._source_bytes) if byte == ord("\n"))]

    def _line_bounds(self, relative: int) -> range:
        """Return byte bounds for one retained source line."""
        start = self._source_line_offsets[relative]
        end = (
            self._source_line_offsets[relative + 1]
            if relative + 1 < len(self._source_line_offsets)
            else len(self._source_bytes)
        )
        return range(start, end)

    def _source_offset(self, line: int, *, column: int) -> int:
        """Translate a provider byte column into the retained declaration source."""
        relative = line - self.span.start_line
        if relative < 0 or relative >= len(self._source_line_offsets):
            raise ValueError(f"syntax node line {line} lies outside {self.key}")
        bounds = self._line_bounds(relative)
        local = column - self.span.start_column if relative == 0 else column
        self._validate_column(line=line, column=column, local=local, bounds=bounds)
        return bounds.start + local

    def _validate_children(
        self,
        *,
        index: int,
        children: Sequence[int],
        parented: bytearray,
    ) -> None:
        """Require each compact child index to exist and have one parent."""
        for child in children:
            if child >= len(self.nodes):
                raise ValueError(f"syntax node {index} names missing child {child}")
            if parented[child]:
                raise ValueError(f"syntax node {child} has more than one parent")
            parented[child] = 1

    def _validate_column(
        self,
        *,
        line: int,
        column: int,
        local: int,
        bounds: range,
    ) -> None:
        """Reject columns beyond a line or inside a UTF-8 character."""
        content = self._source_bytes[bounds.start : bounds.stop]
        if local < 0 or local > len(content.rstrip(b"\r\n")):
            raise ValueError(f"syntax node column {column} lies outside line {line} of {self.key}")
        offset = bounds.start + local
        self._validate_utf8(line=line, column=column, offset=offset)

    def _validate_compact_node(
        self,
        index: int,
        record: SyntaxRecord,
        parented: bytearray,
    ) -> None:
        """Validate one compact node and mark each child as reached once."""
        start = record[2], record[3]
        end = record[4], record[5]
        if end < start:
            raise ValueError(f"syntax node {index} ends before it starts")
        self._validate_node_span(index=index, start=start, end=end)
        self._validate_children(index=index, children=record[6], parented=parented)

    def _validate_compact_tree(self) -> None:
        """Require compact records to describe one complete rooted tree."""
        self._validate_root(self.nodes[0])
        parented = bytearray(len(self.nodes))
        parented[0] = 1
        for index, record in enumerate(self.nodes):
            self._validate_compact_node(index, record, parented)
        if not all(parented):
            raise ValueError("compact syntax records contain a node unreachable from the root")
        self._validate_offsets()

    def _validate_expanded_tree(self, tree: SyntaxElement) -> None:
        """Require one expanded tree to agree with its owning fact."""
        if tree.kind != self.kind:
            raise ValueError(
                f"syntax root kind {tree.kind!r} differs from fact kind {self.kind!r}"
            )
        for node in tree.walk():
            if node.span is not None:
                self._validate_node_path(node)

    def _validate_node_path(self, node: SyntaxElement) -> None:
        """Require one syntax node to belong to this fact's source."""
        if node.span is not None and node.span.path != self.span.path:
            raise ValueError(
                f"syntax node path {node.span.path!r} differs from fact path {self.span.path!r}"
            )

    def _validate_node_span(
        self,
        *,
        index: int,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        """Require one compact node to remain within its declaration."""
        fact_start = self.span.start_line, self.span.start_column
        fact_end = self.span.end_line, self.span.end_column
        if start < fact_start or end > fact_end:
            raise ValueError(f"syntax node {index} lies outside its declaration")

    def _validate_offsets(self) -> None:
        """Require every compact span to address valid UTF-8 boundaries."""
        for record in self.nodes:
            self._source_offset(record[2], column=record[3])
            self._source_offset(record[4], column=record[5])

    def _validate_root(self, root: SyntaxRecord) -> None:
        """Require the compact root identity and span to match its fact."""
        if root[0] != self.kind:
            raise ValueError(f"syntax root kind {root[0]!r} differs from fact kind {self.kind!r}")
        if root[2:6] != self.span_tuple:
            raise ValueError("syntax root span differs from its fact span")

    def _validate_utf8(self, *, line: int, column: int, offset: int) -> None:
        """Reject a provider column that divides one UTF-8 character."""
        if offset < len(self._source_bytes) and self._source_bytes[offset] & 0xC0 == 0x80:
            raise ValueError(
                f"syntax node column {column} divides a UTF-8 character on line {line} "
                f"of {self.key}"
            )
