from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast

from hypothesis import strategies as st

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    ClassFact,
    FunctionFact,
    ModuleFact,
    OverrideFact,
    SourceSpan,
    SymbolReach,
    SymbolReachFact,
)
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.table import AnalysisSession, ClassRelation, FunctionRelation

from ...support import query_value, retained_query, written

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.plugins import Fact, Table

_IDENTIFIER = st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=6)


def native_query[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one specialized rule once over the complete native table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic surface rule returned a model query")
    return result


def class_table(sources: dict[str, str]) -> Table[ClassFact]:
    """Parse one corpus into specialized native class relations."""
    with TemporaryDirectory() as directory:
        return AnalysisSession(
            written(Path(directory), sources),
            suffixes=(".py",),
            typed_families=(ClassFact,),
        ).class_tables()


def function_table(sources: dict[str, str]) -> Table[FunctionFact]:
    """Parse one corpus into specialized native function relations."""
    with TemporaryDirectory() as directory:
        return AnalysisSession(
            written(Path(directory), sources),
            suffixes=(".py",),
            typed_families=(FunctionFact,),
        ).function_tables()


def class_values(result: RuleQuery, subject: Table[ClassFact]) -> dict[str, RuleValue]:
    """Return each module's class-rule value by source path."""
    facts = subject.frame(ClassRelation.FACTS).select("fact_id", "path")
    rows = result.values.collect().join(facts, on=["fact_id", "path"])
    return {cast("str", row["path"]): scalar_row_value(row) for row in rows.iter_rows(named=True)}


def function_values(result: RuleQuery, subject: Table[FunctionFact]) -> dict[str, RuleValue]:
    """Return each callable's function-rule value by source-level name."""
    functions = subject.frame(FunctionRelation.FUNCTIONS).select("fact_id", "name")
    rows = result.values.collect().join(functions, on="fact_id")
    return {cast("str", row["name"]): scalar_row_value(row) for row in rows.iter_rows(named=True)}


def retained_value(subject: Fact, rule: RuleContract, **settings: RuleSetting) -> RuleValue:
    """Return one scalar from a generic rule invoked once over retained evidence."""
    return query_value(retained_query(subject, rule, **settings))


def reach(*declarations: SymbolReach) -> SymbolReachFact:
    """Return one reach fact holding the given resolved declarations of a module."""
    return SymbolReachFact(
        key="reach:src/service.py",
        span=SourceSpan(path="src/service.py"),
        declarations=list(declarations),
    )


def attribute(qualname: str) -> SymbolReach:
    """Return one resolved data member of the type its qualified name names."""
    return SymbolReach(qualname=qualname, kind="attribute", span=SourceSpan(path="src/service.py"))


def link(derived: str, *, base: str, depth: int = 1, **changes: Sequence[str]) -> OverrideFact:
    """Return one inheritance link between a derived class and one of its ancestors."""
    return OverrideFact.model_validate(
        {
            "key": f"override:{derived}:{base}",
            "span": SourceSpan(path="src/service.py"),
            "derived": derived,
            "base": base,
            "depth": depth,
        }
        | changes
    )


def module(path: str) -> ModuleFact:
    """Return one module fact located at the given repository-relative path."""
    return ModuleFact(key=f"module:{path}", span=SourceSpan(path=path))
