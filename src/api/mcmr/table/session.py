import sys
from typing import TYPE_CHECKING, cast

from ..facts import (
    AttributeAccessFact,
    CallFact,
    ClassFact,
    Fact,
    FunctionFact,
    ImportBindingFact,
    StringExpressionFact,
    SyntaxFact,
)
from ..kernel import KernelStats, buildable
from ..kernel_tables import AnalysisSession as NativeAnalysisSession
from ..kernel_tables import SessionStats
from .models import generic_table, table_schema, typed_table
from .names import (
    CallRelation,
    ClassRelation,
    FunctionRelation,
    ImportBindingRelation,
    SyntaxRelation,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence
    from pathlib import Path

    from .models import Table

_specialized_families = {
    fact.__name__
    for fact in (
        AttributeAccessFact,
        CallFact,
        ClassFact,
        FunctionFact,
        ImportBindingFact,
        StringExpressionFact,
        SyntaxFact,
    )
}


class AnalysisSession:
    """Own one repository parse and release each selected table after use."""

    def __init__(
        self,
        root: Path,
        *,
        suffixes: Sequence[str] | None = None,
        typed_families: Sequence[str] | None = None,
    ) -> None:
        selected = [FunctionFact.__name__] if typed_families is None else list(typed_families)
        self.session = NativeAnalysisSession(
            root,
            selected,
            python_standard_library=sorted(sys.stdlib_module_names),
            suffixes=None if not suffixes else list(suffixes),
            generic_schemas=self._generic_schemas(selected),
        )

    @property
    def stats(self) -> SessionStats:
        """Return native measurements from this repository pass."""
        return self.session.stats()

    def call_tables(self) -> Table[CallFact]:
        """Move resolved call rows into normalized eager frames."""
        return typed_table(self.session.call_tables(), family=CallFact, relation_type=CallRelation)

    def class_tables(self) -> Table[ClassFact]:
        """Move graph-enriched class rows into normalized eager frames."""
        return typed_table(
            self.session.class_tables(), family=ClassFact, relation_type=ClassRelation
        )

    def function_tables(self) -> Table[FunctionFact]:
        """Move callable rows into normalized eager frames."""
        return typed_table(
            self.session.function_tables(),
            family=FunctionFact,
            relation_type=FunctionRelation,
        )

    def import_binding_tables(self) -> Table[ImportBindingFact]:
        """Move imported bindings into normalized eager frames."""
        return typed_table(
            self.session.import_binding_tables(),
            family=ImportBindingFact,
            relation_type=ImportBindingRelation,
        )

    def kernel_stats(self, total_nanoseconds: int) -> KernelStats:
        """Return measurements in the public kernel statistics contract."""
        native = self.stats
        values = {
            name: getattr(native, name)
            for name in KernelStats.model_fields
            if hasattr(native, name)
        }
        return KernelStats.model_validate(values | {"total_nanoseconds": total_nanoseconds})

    def syntax_tables(self) -> Table[SyntaxFact]:
        """Move compact declaration trees into normalized eager frames."""
        return typed_table(
            self.session.syntax_tables(), family=SyntaxFact, relation_type=SyntaxRelation
        )

    def table[Family: Fact](self, family: type[Family]) -> Table[Family]:
        """Move any selected family into its exact normalized relation contract."""
        families = FunctionFact, CallFact, ClassFact, ImportBindingFact, SyntaxFact
        builders: tuple[Callable[[], Table[Fact]], ...]
        builders = self.function_tables, self.call_tables, self.class_tables
        builders += self.import_binding_tables, self.syntax_tables
        specialized = dict(zip(families, builders, strict=True)).get(family)
        if specialized:
            return cast("Table[Family]", specialized())
        return generic_table(family, self.session.table(family.__name__))

    def table_markers(self) -> Generator[str]:
        """Yield selected table family names in kernel order."""
        while (family := self.session.next_table_marker()) is not None:
            yield family

    @staticmethod
    def _generic_schemas(selected: Sequence[str]) -> dict[str, str]:
        """Compile schemas only for families without native specialized tables."""
        families = buildable()
        return {
            name: table_schema(families[name])
            for name in selected
            if name not in _specialized_families
        }
