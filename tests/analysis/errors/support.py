from pathlib import Path
from typing import TYPE_CHECKING

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import SyntaxFact
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.table import AnalysisSession, SyntaxRelation, Table

if TYPE_CHECKING:
    from collections.abc import Mapping


def table(root: Path, sources: Mapping[str, str]) -> Table[SyntaxFact]:
    """Parse one multilingual error corpus into native syntax relations."""
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return AnalysisSession(
        root,
        suffixes=sorted({Path(name).suffix for name in sources}),
        typed_families=(SyntaxFact.__name__,),
    ).syntax_tables()


def query(
    rule: RuleContract,
    subject: Table[SyntaxFact],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one error rule once over every declaration in the repository table."""
    result = rule.invoke_table(
        subject,
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic error rule returned a model query")
    return result


def value(result: RuleQuery, subject: Table[SyntaxFact], qualname: str) -> RuleValue:
    """Return one declaration's scalar from a completed repository query."""
    facts = subject.frame(SyntaxRelation.FACTS).select("fact_id", "qualname")
    values = result.values.collect().join(facts, on="fact_id")
    return scalar_frame_value(values.filter(values["qualname"] == qualname))
