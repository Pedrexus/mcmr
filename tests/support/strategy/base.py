import typing
from typing import TYPE_CHECKING, TypeAliasType

import annotated_types
from hypothesis import strategies as st
from patos import FrozenModel
from pydantic import BaseModel, PositiveInt, ValidationError
from pydantic.fields import FieldInfo

from mcmr.facts import SourceSpan, SyntaxFact, SyntaxNode

from ..vocabulary import neutral_words

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ..fixtures import FactValue

_NEUTRAL = neutral_words()


class SchemaStrategyBase(FrozenModel):
    """Own shared scalar domains and correlated syntax normalization."""

    dialect: dict[str, list[str]] = {"": _NEUTRAL}
    recursive_leaf_budget: PositiveInt = 2
    collection_size_budget: PositiveInt = 2

    @staticmethod
    def _interval(
        metadata: Sequence[
            FieldInfo | annotated_types.BaseMetadata | annotated_types.GroupedMetadata
        ],
    ) -> dict[str, float]:
        """Read the closed interval one annotation declares, however Pydantic spelled it."""
        found: dict[str, float] = {}
        for item in metadata:
            match item:
                case FieldInfo():
                    found |= SchemaStrategyBase._interval(item.metadata)
                case annotated_types.GroupedMetadata():
                    grouped = typing.cast("list[annotated_types.BaseMetadata]", list(item))
                    found |= SchemaStrategyBase._interval(grouped)
                case annotated_types.Ge(ge=int() | float() as bound):
                    found["minimum"] = bound
                case annotated_types.Gt(gt=int() | float() as bound):
                    found["minimum"] = bound + 1
                case annotated_types.Le(le=int() | float() as bound):
                    found["maximum"] = bound
                case annotated_types.Lt(lt=int() | float() as bound):
                    found["maximum"] = bound - 1
                case annotated_types.MinLen(min_length=int() as bound):
                    found["minimum_length"] = bound
                case annotated_types.MaxLen(max_length=int() as bound):
                    found["maximum_length"] = bound
        return found

    @staticmethod
    def _located_tree(node: SyntaxNode, path: str, kind: str | None = None) -> SyntaxNode:
        """Give a generated fixture tree one root kind, one path, and locally owned text."""
        return node.model_copy(
            update={
                "kind": node.kind if kind is None else kind,
                "text": node.text or node.name or "value",
                "span": node.span.model_copy(update={"path": path}) if node.span else None,
                "children": [
                    SchemaStrategyBase._located_tree(child, path) for child in node.children
                ],
            }
        )

    @staticmethod
    def _number(
        annotation: type | TypeAliasType | None, interval: Mapping[str, float]
    ) -> st.SearchStrategy[int | float]:
        """Build an integer or finite float from its declared interval."""
        if annotation is float:
            return st.floats(
                min_value=interval.get("minimum", -8.0),
                max_value=interval.get("maximum", 120.0),
                allow_nan=False,
                allow_infinity=False,
            )
        low = int(interval.get("minimum", -8))
        high = int(interval.get("maximum", max(40, low + 20)))
        near = [value for value in (low, low + 1, 0, 1, 2, 3, high) if low <= value <= high]
        spread = st.integers(min_value=low, max_value=high)
        return st.sampled_from(near) | spread if near else spread

    @staticmethod
    def _syntax_fact(values: dict[str, FactValue]) -> SyntaxFact:
        """Build one expanded syntax fixture whose correlated fields describe the same tree."""
        span = typing.cast("SourceSpan", values["span"])
        kind = typing.cast("str", values["kind"])
        tree = typing.cast("SyntaxNode | None", values["tree"])
        if tree is not None:
            values["tree"] = SchemaStrategyBase._located_tree(tree, span.path, kind)
        return SyntaxFact.model_validate(values)

    @staticmethod
    def _valid[Model: BaseModel](model: type[Model], values: dict[str, FactValue]) -> bool:
        """Whether one generated field set satisfies the model's relational contracts."""
        try:
            model.model_validate(values)
        except ValidationError:
            return False
        return True

    def _source_spans(self) -> st.SearchStrategy[SourceSpan]:
        """Build source ranges whose end follows their start."""
        return st.tuples(
            self._words("path"),
            st.integers(min_value=1, max_value=40),
            st.integers(min_value=0, max_value=40),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=40),
        ).map(
            lambda stated: SourceSpan(
                path=stated[0],
                start_line=stated[1],
                start_column=stated[2],
                end_line=stated[1] + stated[3],
                end_column=stated[2] + stated[4] if stated[3] == 0 else stated[4],
            )
        )

    def _string(self, name: str, interval: Mapping[str, float]) -> st.SearchStrategy[str]:
        """Build a word within the declared length interval."""
        minimum = int(interval.get("minimum_length", 0))
        maximum = int(interval["maximum_length"]) if "maximum_length" in interval else None
        return self._words(name).filter(
            lambda value: len(value) >= minimum and (maximum is None or len(value) <= maximum)
        )

    def _words(self, name: str) -> st.SearchStrategy[str]:
        """Return neutral words together with rule vocabulary for one field."""
        pool = self.dialect.get(name) or self.dialect[""]
        return st.sampled_from(_NEUTRAL) | st.sampled_from(pool)
