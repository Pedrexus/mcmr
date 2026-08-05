import types
import typing
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAliasType

from hypothesis import strategies as st
from pydantic import BaseModel

from mcmr.facts import (
    CloneFragment,
    CloneGroupFact,
    Evidence,
    Expression,
    FileHistory,
    HistoryChange,
    MappingEntry,
    RepositoryHistoryFact,
    SourceSpan,
    SyntaxFact,
    SyntaxNode,
)

from .base import SchemaStrategyBase

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import annotated_types
    from pydantic.fields import FieldInfo

    from ..fixtures import FactValue


class SchemaStrategy(SchemaStrategyBase):
    """Derive bounded Hypothesis strategies directly from each fact model's declared schema."""

    def of[Model: BaseModel](
        self,
        model: type[Model],
        trail: Sequence[type[BaseModel]] | None = None,
    ) -> st.SearchStrategy[Model]:
        """Return the strategy building one validated instance of this model."""
        trail = trail or []
        builders: dict[type[BaseModel], Callable[[], st.SearchStrategy[BaseModel]]] = {
            Expression: lambda: self._expressions(trail),
            SourceSpan: self._source_spans,
            SyntaxNode: lambda: self._syntax_nodes(trail),
            CloneGroupFact: lambda: self._clone_group(trail),
            RepositoryHistoryFact: lambda: self._repository_history(trail),
        }
        if (builder := builders.get(model)) is not None:
            return typing.cast("st.SearchStrategy[Model]", builder())
        if model is SyntaxFact:
            nested: list[type[BaseModel]] = [*trail, model]
            fields = {
                name: self._field(
                    field.annotation, metadata=field.metadata, trail=nested, name=name
                )
                for name, field in model.model_fields.items()
            }
            fields["nodes"] = st.just([])
            return typing.cast(
                "st.SearchStrategy[Model]",
                st.fixed_dictionaries(fields).map(self._syntax_fact),
            )
        return self._model(model, trail)

    def _clone_group(self, trail: Sequence[type[BaseModel]]) -> st.SearchStrategy[CloneGroupFact]:
        """Build clone spans and repository sizes from one shared line count."""
        nested: list[type[BaseModel]] = [*trail, CloneGroupFact]
        positions = st.lists(
            st.tuples(self._words("path"), st.integers(min_value=1, max_value=40)),
            min_size=2,
            max_size=max(2, self.collection_size_budget),
            unique_by=lambda position: position[0],
        )
        return st.tuples(st.integers(min_value=1, max_value=20), positions).flatmap(
            lambda claim: self._clone_group_with(claim[0], positions=claim[1], trail=nested)
        )

    def _clone_group_with(
        self,
        line_count: int,
        *,
        positions: Sequence[tuple[str, int]],
        trail: Sequence[type[BaseModel]],
    ) -> st.SearchStrategy[CloneGroupFact]:
        """Build one valid group around an already chosen repeated range."""
        fields = CloneGroupFact.model_fields
        fragments = [
            CloneFragment(
                path=path,
                start_line=start,
                end_line=start + line_count - 1,
            )
            for path, start in positions
        ]
        repeated = line_count * (len(fragments) - 1)
        return st.builds(
            CloneGroupFact,
            key=self._field(
                fields["key"].annotation, metadata=fields["key"].metadata, trail=trail, name="key"
            ),
            span=self._field(
                fields["span"].annotation,
                metadata=fields["span"].metadata,
                trail=trail,
                name="span",
            ),
            language=self._field(
                fields["language"].annotation,
                metadata=fields["language"].metadata,
                trail=trail,
                name="language",
            ),
            evidence=self._field(
                fields["evidence"].annotation,
                metadata=fields["evidence"].metadata,
                trail=trail,
                name="evidence",
            ),
            fragments=st.just(fragments),
            token_length=self._field(
                fields["token_length"].annotation,
                metadata=fields["token_length"].metadata,
                trail=trail,
                name="token_length",
            ),
            repository_line_count=st.integers(min_value=repeated, max_value=repeated + 40),
        )

    def _collection_field(
        self,
        annotation: type | TypeAliasType | None,
        trail: Sequence[type[BaseModel]],
        name: str,
    ) -> st.SearchStrategy[FactValue]:
        """Return the strategy for one concrete collection annotation."""
        origin, arguments = typing.get_origin(annotation), typing.get_args(annotation)
        if origin is list:
            elements = self._field(arguments[0], metadata=(), trail=trail, name=name)
            if arguments[0] is Evidence:
                claims = typing.cast("st.SearchStrategy[Evidence]", elements)
                return typing.cast(
                    "st.SearchStrategy[FactValue]",
                    st.lists(
                        claims,
                        max_size=self.collection_size_budget,
                        unique_by=lambda claim: claim.signal,
                    ),
                )
            return st.lists(elements, max_size=self.collection_size_budget)
        if origin is tuple:
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return st.lists(
                    self._field(arguments[0], metadata=(), trail=trail, name=name),
                    max_size=self.collection_size_budget,
                ).map(tuple)
            return st.tuples(
                *[self._field(item, metadata=(), trail=trail, name=name) for item in arguments]
            )
        return st.dictionaries(
            self._words(name),
            self._field(arguments[1], metadata=(), trail=trail, name=name),
            max_size=self.collection_size_budget,
        )

    def _concrete_scalar(
        self,
        annotation: type | TypeAliasType,
        interval: Mapping[str, float],
        trail: Sequence[type[BaseModel]],
        name: str,
    ) -> st.SearchStrategy[FactValue]:
        """Build one non-null scalar from its concrete declared type."""
        if annotation in (int, float):
            return self._number(annotation, interval)
        if annotation is str:
            return self._string(name, interval)
        if isinstance(annotation, type):
            return self._declared_type(annotation, trail)
        raise TypeError(f"no strategy states the domain of {annotation!r}")

    def _declared_type(
        self, annotation: type, trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[FactValue]:
        """Build an enum or nested Pydantic model leaf."""
        if issubclass(annotation, StrEnum):
            return st.sampled_from(list(annotation))
        if issubclass(annotation, BaseModel):
            return self._nested_model(annotation, trail)
        raise TypeError(f"no strategy states the domain of {annotation!r}")

    def _expression_with(
        self,
        trail: Sequence[type[BaseModel]],
        *,
        arguments: st.SearchStrategy[list[Expression]],
        entries: st.SearchStrategy[list[MappingEntry]],
    ) -> st.SearchStrategy[Expression]:
        """Build one expression layer around supplied child strategies."""
        fields = Expression.model_fields
        return st.builds(
            Expression,
            text=self._field(
                fields["text"].annotation,
                metadata=fields["text"].metadata,
                trail=trail,
                name="text",
            ),
            qualified_name=self._field(
                fields["qualified_name"].annotation,
                metadata=fields["qualified_name"].metadata,
                trail=trail,
                name="qualified_name",
            ),
            literal_kind=self._field(
                fields["literal_kind"].annotation,
                metadata=fields["literal_kind"].metadata,
                trail=trail,
                name="literal_kind",
            ),
            resolved_type=self._field(
                fields["resolved_type"].annotation,
                metadata=fields["resolved_type"].metadata,
                trail=trail,
                name="resolved_type",
            ),
            arguments=arguments,
            entries=entries,
            node=self._field(
                fields["node"].annotation,
                metadata=fields["node"].metadata,
                trail=trail,
                name="node",
            ),
        )

    def _expressions(self, trail: Sequence[type[BaseModel]]) -> st.SearchStrategy[Expression]:
        """Build expressions to arbitrary recursive depth through Hypothesis tree growth."""
        nested: list[type[BaseModel]] = [*trail, Expression]
        base = self._expression_with(nested, arguments=st.just([]), entries=st.just([]))
        return st.recursive(
            base,
            lambda children: self._expression_with(
                nested,
                arguments=st.lists(children, max_size=self.collection_size_budget),
                entries=st.lists(
                    st.builds(MappingEntry, key=self._words("key"), value=children),
                    max_size=self.collection_size_budget,
                ),
            ),
            max_leaves=self.recursive_leaf_budget,
        )

    def _field(
        self,
        annotation: type | TypeAliasType | None,
        *,
        metadata: Sequence[
            FieldInfo | annotated_types.BaseMetadata | annotated_types.GroupedMetadata
        ],
        trail: Sequence[type[BaseModel]],
        name: str = "",
    ) -> st.SearchStrategy[FactValue]:
        """Return the strategy one declared field admits, following its own annotation."""
        origin, arguments = typing.get_origin(annotation), typing.get_args(annotation)
        if isinstance(annotation, TypeAliasType) or origin is typing.Annotated:
            value = annotation.__value__ if isinstance(annotation, TypeAliasType) else arguments[0]
            additions = [] if isinstance(annotation, TypeAliasType) else list(arguments[1:])
            return self._field(value, metadata=[*metadata, *additions], trail=trail, name=name)
        if origin in (types.UnionType, typing.Union):
            return st.one_of(
                [
                    self._field(item, metadata=metadata, trail=trail, name=name)
                    for item in arguments
                ]
            )
        if origin in (list, tuple, dict):
            return self._collection_field(annotation, trail, name)
        if origin is typing.Literal:
            return st.sampled_from(arguments)
        return self._scalar(annotation, self._interval(metadata), trail, name)

    def _file_history(
        self, total: int, trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[FileHistory]:
        """Build one file whose authors and commits fit the repository total."""
        fields = FileHistory.model_fields
        return st.integers(min_value=1, max_value=total).flatmap(
            lambda commits: st.integers(min_value=1, max_value=commits).flatmap(
                lambda authors: st.builds(
                    FileHistory,
                    path=self._field(
                        fields["path"].annotation,
                        metadata=fields["path"].metadata,
                        trail=trail,
                        name="path",
                    ),
                    author_count=st.just(authors),
                    additional_commit_count=st.just(commits - authors),
                    days_since_last_change=self._field(
                        fields["days_since_last_change"].annotation,
                        metadata=fields["days_since_last_change"].metadata,
                        trail=trail,
                        name="days_since_last_change",
                    ),
                    line_count=self._field(
                        fields["line_count"].annotation,
                        metadata=fields["line_count"].metadata,
                        trail=trail,
                        name="line_count",
                    ),
                    is_test=self._field(
                        fields["is_test"].annotation,
                        metadata=fields["is_test"].metadata,
                        trail=trail,
                        name="is_test",
                    ),
                    imports=self._field(
                        fields["imports"].annotation,
                        metadata=fields["imports"].metadata,
                        trail=trail,
                        name="imports",
                    ),
                )
            )
        )

    def _history_change(
        self, trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[HistoryChange]:
        """Build one change with unique requested paths and an independently sized remainder."""
        fields = HistoryChange.model_fields
        paths = st.lists(
            self._words("paths").filter(bool),
            min_size=1,
            max_size=self.collection_size_budget,
            unique=True,
        )
        return st.builds(
            HistoryChange,
            other_file_count=self._field(
                fields["other_file_count"].annotation,
                metadata=fields["other_file_count"].metadata,
                trail=trail,
                name="other_file_count",
            ),
            paths=paths,
        )

    def _history_with_total(
        self, total: int, trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[RepositoryHistoryFact]:
        """Build one history whose files and scoped changes fit its total commits."""
        nested: list[type[BaseModel]] = [*trail, RepositoryHistoryFact]
        changes = st.lists(
            self._history_change(nested), max_size=min(total, self.collection_size_budget)
        )
        files = (
            st.lists(
                self._file_history(total, nested),
                max_size=self.collection_size_budget,
                unique_by=lambda record: record.path,
            )
            if total
            else st.just([])
        )
        fields = RepositoryHistoryFact.model_fields
        return changes.flatmap(
            lambda held: st.builds(
                RepositoryHistoryFact,
                key=self._field(
                    fields["key"].annotation,
                    metadata=fields["key"].metadata,
                    trail=nested,
                    name="key",
                ),
                span=self._field(
                    fields["span"].annotation,
                    metadata=fields["span"].metadata,
                    trail=nested,
                    name="span",
                ),
                language=self._field(
                    fields["language"].annotation,
                    metadata=fields["language"].metadata,
                    trail=nested,
                    name="language",
                ),
                evidence=self._field(
                    fields["evidence"].annotation,
                    metadata=fields["evidence"].metadata,
                    trail=nested,
                    name="evidence",
                ),
                unscoped_commit_count=st.just(total - len(held)),
                files=files,
                changes=st.just(held),
            )
        )

    def _model[Model: BaseModel](
        self, model: type[Model], trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[Model]:
        """Build one ordinary model from its declared fields and validators."""
        nested: list[type[BaseModel]] = [*trail, model]
        fields = {
            name: self._field(field.annotation, metadata=field.metadata, trail=nested, name=name)
            for name, field in model.model_fields.items()
        }
        relational = set(model.__pydantic_decorators__.model_validators) - {
            "evidence_ids_are_unique"
        }
        if not relational:
            return st.builds(model, **fields)
        candidates = st.fixed_dictionaries(fields)
        valid = candidates.filter(lambda values: self._valid(model, values))
        return valid.map(model.model_validate)

    def _nested_model(
        self, annotation: type[BaseModel], trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[BaseModel]:
        """Build a nested model unless it needs a dedicated recursive strategy."""
        if annotation in trail:
            raise TypeError(f"recursive model {annotation.__name__} needs a tree strategy")
        return self.of(annotation, trail)

    def _repository_history(
        self, trail: Sequence[type[BaseModel]]
    ) -> st.SearchStrategy[RepositoryHistoryFact]:
        """Build history counts from one total so their cross-record contract cannot filter."""
        return st.integers(min_value=0, max_value=40).flatmap(
            lambda total: self._history_with_total(total, trail)
        )

    def _scalar(
        self,
        annotation: type | TypeAliasType | None,
        interval: Mapping[str, float],
        trail: Sequence[type[BaseModel]],
        name: str,
    ) -> st.SearchStrategy[FactValue]:
        """Return the strategy one leaf annotation admits, inside the interval it declares."""
        if annotation is None or annotation is type(None):
            return st.none()
        if annotation is bool:
            return st.booleans()
        return self._concrete_scalar(annotation, interval, trail, name)

    def _syntax_node_with(
        self,
        trail: Sequence[type[BaseModel]],
        children: st.SearchStrategy[list[SyntaxNode]],
    ) -> st.SearchStrategy[SyntaxNode]:
        """Build one syntax layer around a supplied child strategy."""
        fields = SyntaxNode.model_fields
        return st.builds(
            SyntaxNode,
            kind=self._field(
                fields["kind"].annotation,
                metadata=fields["kind"].metadata,
                trail=trail,
                name="kind",
            ),
            name=self._field(
                fields["name"].annotation,
                metadata=fields["name"].metadata,
                trail=trail,
                name="name",
            ),
            text=self._field(
                fields["text"].annotation,
                metadata=fields["text"].metadata,
                trail=trail,
                name="text",
            ),
            span=self._field(
                fields["span"].annotation,
                metadata=fields["span"].metadata,
                trail=trail,
                name="span",
            ),
            children=children,
        )

    def _syntax_nodes(self, trail: Sequence[type[BaseModel]]) -> st.SearchStrategy[SyntaxNode]:
        """Build syntax nodes to arbitrary recursive depth through Hypothesis tree growth."""
        nested: list[type[BaseModel]] = [*trail, SyntaxNode]
        return st.recursive(
            self._syntax_node_with(nested, st.just([])),
            lambda children: self._syntax_node_with(
                nested, st.lists(children, max_size=self.collection_size_budget)
            ),
            max_leaves=self.recursive_leaf_budget,
        )
