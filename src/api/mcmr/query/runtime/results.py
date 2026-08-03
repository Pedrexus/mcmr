from functools import cached_property
from typing import TYPE_CHECKING

import polars as pl
from patos import FrozenModel, Runtime

from ...checking.evaluations import Evaluation
from ...domain.contracts import (
    Choice,
    Edit,
    Finding,
    FixPlan,
    FixSafety,
    ImportRequest,
    Inline,
    Measurement,
    ModelProvenance,
    Move,
    Placement,
    Remove,
    RemoveDirectory,
    Rename,
    Replace,
    Unit,
    Unwrap,
)
from ...facts import NodeRef, SourceSpan, SymbolRef
from ..schema.values import frame_value, scalar_frame_value

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from ...domain.contracts import RuleValue

type Rewrite = Remove | RemoveDirectory | Replace | Move | Unwrap | Rename | Inline
type ResultKey = tuple[str, str]
type RewriteKey = tuple[str, str, int]
type RewriteConstructor = Callable[
    [int, Mapping[str, Sequence[NodeRef]], Sequence[ImportRequest]],
    Rewrite,
]


class QueryEvaluations(FrozenModel):
    """Materialize public failure evidence directly from compact query rows."""

    failures: Runtime[pl.DataFrame]
    findings: Runtime[pl.DataFrame]
    fix_rewrites: Runtime[pl.DataFrame]
    fix_nodes: Runtime[pl.DataFrame]
    fix_imports: Runtime[pl.DataFrame]

    @cached_property
    def imports_by_rewrite(self) -> dict[RewriteKey, list[ImportRequest]]:
        """Group requested imports by their owning replacement rewrite."""
        grouped: dict[RewriteKey, list[ImportRequest]] = {}
        for index in range(self.fix_imports.height):
            key = self._rewrite_key(self.fix_imports, index)
            grouped.setdefault(key, []).append(
                ImportRequest(
                    module=frame_value(self.fix_imports, index, "module", str),
                    name=frame_value(self.fix_imports, index, "name", str),
                    alias=frame_value(self.fix_imports, index, "alias", str),
                    level=frame_value(self.fix_imports, index, "level", int),
                    type_only=frame_value(self.fix_imports, index, "type_only", bool),
                )
            )
        return grouped

    @cached_property
    def nodes_by_rewrite(self) -> dict[RewriteKey, dict[str, list[NodeRef]]]:
        """Group normalized node handles by rewrite and semantic role."""
        grouped: dict[RewriteKey, dict[str, list[NodeRef]]] = {}
        for index in range(self.fix_nodes.height):
            key = self._rewrite_key(self.fix_nodes, index)
            role = frame_value(self.fix_nodes, index, "role", str)
            node = NodeRef(
                id=frame_value(self.fix_nodes, index, "id", str),
                span=self._source_span(self.fix_nodes, index),
                kind=frame_value(self.fix_nodes, index, "kind", str),
                text=frame_value(self.fix_nodes, index, "text", str),
            )
            grouped.setdefault(key, {}).setdefault(role, []).append(node)
        return grouped

    def evaluations(self) -> Iterator[Evaluation]:
        """Yield failed evaluations in stable repository and rule order."""
        grouped = self._grouped_findings()
        return (self._evaluation(index, grouped) for index in range(self.failures.height))

    def rewrite(
        self,
        index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        imports: Sequence[ImportRequest],
    ) -> Rewrite:
        """Build one typed rewrite from its main row and role-keyed nodes."""
        constructors: dict[str, RewriteConstructor] = {
            "inline": self._inline,
            "move": self._move,
            "remove": self._remove,
            "remove-directory": self._remove_directory,
            "rename": self._rename,
            "replace": self._replace,
            "unwrap": self._unwrap,
        }
        kind = frame_value(self.fix_rewrites, index, "kind", str)
        try:
            return constructors[kind](index, nodes, imports)
        except KeyError:
            raise ValueError(f"unknown table rewrite kind {kind}") from None

    def value(self, index: int) -> RuleValue:
        """Return the one populated scalar column for a failed observation."""
        return scalar_frame_value(self.failures, index)

    @staticmethod
    def _result_key(frame: pl.DataFrame, index: int) -> ResultKey:
        return (
            frame_value(frame, index, "rule", str),
            frame_value(frame, index, "fact_id", str),
        )

    @staticmethod
    def _rewrite_key(frame: pl.DataFrame, index: int) -> RewriteKey:
        rule, fact_id = QueryEvaluations._result_key(frame, index)
        return rule, fact_id, frame_value(frame, index, "rewrite_order", int)

    @staticmethod
    def _source_span(frame: pl.DataFrame, index: int) -> SourceSpan:
        return SourceSpan(
            path=frame_value(frame, index, "path", str),
            start_line=frame_value(frame, index, "start_line", int),
            start_column=frame_value(frame, index, "start_column", int),
            end_line=frame_value(frame, index, "end_line", int),
            end_column=frame_value(frame, index, "end_column", int),
        )

    def _choice(self, index: int) -> Choice | None:
        question = frame_value(self.findings, index, "choice_question", str)
        return (
            Choice(
                question=question,
                options=frame_value(self.findings, index, "choice_options", list),
            )
            if question
            else None
        )

    def _edit(self, rows: Sequence[tuple[int, Rewrite]]) -> Edit:
        index = rows[0][0]
        return Edit(
            plan=FixPlan(
                summary=frame_value(self.fix_rewrites, index, "summary", str),
                rewrites=[rewrite for _, rewrite in rows],
            ),
            safety=FixSafety(frame_value(self.fix_rewrites, index, "safety", str)),
        )

    def _evaluation(
        self,
        index: int,
        findings: Mapping[ResultKey, list[Finding]],
    ) -> Evaluation:
        rule, fact_id = self._result_key(self.failures, index)
        return Evaluation(
            rule=rule,
            fact=fact_id,
            value=self.value(index),
            span=self._source_span(self.failures, index),
            findings=findings.get((rule, fact_id), []),
        )

    def _finding(self, index: int, edit: Edit | None) -> Finding:
        return Finding(
            message=frame_value(self.findings, index, "message", str),
            span=self._source_span(self.findings, index),
            measurements=self._measurements(index),
            evidence=frame_value(self.findings, index, "evidence", list),
            provenance=self._provenance(index),
            repair=self._choice(index) or edit,
        )

    def _grouped_edits(self) -> dict[ResultKey, Edit]:
        grouped: dict[ResultKey, list[tuple[int, Rewrite]]] = {}
        for index in range(self.fix_rewrites.height):
            key = self._result_key(self.fix_rewrites, index)
            rewrite_key = (*key, frame_value(self.fix_rewrites, index, "rewrite_order", int))
            rewrite = self.rewrite(
                index,
                self.nodes_by_rewrite.get(rewrite_key, {}),
                self.imports_by_rewrite.get(rewrite_key, []),
            )
            grouped.setdefault(key, []).append((index, rewrite))
        return {key: self._edit(rows) for key, rows in grouped.items()}

    def _grouped_findings(self) -> dict[ResultKey, list[Finding]]:
        grouped: dict[ResultKey, list[Finding]] = {}
        repairs = self._grouped_edits()
        for index in range(self.findings.height):
            key = self._result_key(self.findings, index)
            grouped.setdefault(key, []).append(self._finding(index, repairs.get(key)))
        return grouped

    def _inline(
        self,
        _index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        _imports: Sequence[ImportRequest],
    ) -> Inline:
        return Inline(
            declaration=nodes["declaration"][0],
            body=nodes["body"][0],
            references=list(nodes.get("reference", [])),
        )

    def _measurements(self, index: int) -> list[Measurement]:
        names = frame_value(self.findings, index, "measurement_names", list)
        values = frame_value(self.findings, index, "measurement_values", list)
        units = frame_value(self.findings, index, "measurement_units", list)
        return [
            Measurement(name=name, value=value, unit=Unit(unit))
            for name, value, unit in zip(names, values, units, strict=True)
        ]

    def _move(
        self,
        index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        imports: Sequence[ImportRequest],
    ) -> Move:
        return Move(
            target=nodes["target"][0],
            anchor=nodes["anchor"][0],
            placement=Placement(frame_value(self.fix_rewrites, index, "placement", str)),
            prefix=frame_value(self.fix_rewrites, index, "source", str),
            imports=list(imports),
        )

    def _provenance(self, index: int) -> ModelProvenance | None:
        provenance = {
            name.removeprefix("provenance_"): value
            for name, value in self.findings.row(index, named=True).items()
            if name.startswith("provenance_")
        }
        return ModelProvenance.model_validate(provenance) if provenance["backend"] else None

    def _remove(
        self,
        _index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        _imports: Sequence[ImportRequest],
    ) -> Remove:
        return Remove(target=nodes["target"][0])

    def _remove_directory(
        self,
        index: int,
        _nodes: Mapping[str, Sequence[NodeRef]],
        _imports: Sequence[ImportRequest],
    ) -> RemoveDirectory:
        return RemoveDirectory(
            target=SourceSpan(path=frame_value(self.fix_rewrites, index, "source", str))
        )

    def _rename(
        self,
        index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        _imports: Sequence[ImportRequest],
    ) -> Rename:
        symbol = SymbolRef(
            id=frame_value(self.fix_rewrites, index, "symbol_id", str),
            name=frame_value(self.fix_rewrites, index, "symbol_name", str),
            declaration=nodes["declaration"][0],
            references=list(nodes.get("reference", [])),
            are_references_complete=frame_value(
                self.fix_rewrites, index, "references_complete", bool
            ),
        )
        return Rename(symbol=symbol, name=frame_value(self.fix_rewrites, index, "name", str))

    def _replace(
        self,
        index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        imports: Sequence[ImportRequest],
    ) -> Replace:
        return Replace(
            target=nodes["target"][0],
            source=frame_value(self.fix_rewrites, index, "source", str),
            imports=list(imports),
        )

    def _unwrap(
        self,
        _index: int,
        nodes: Mapping[str, Sequence[NodeRef]],
        _imports: Sequence[ImportRequest],
    ) -> Unwrap:
        return Unwrap(target=nodes["target"][0], keep=nodes["keep"][0])
