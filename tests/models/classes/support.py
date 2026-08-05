from typing import TYPE_CHECKING

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import ClassFact
from mcmr.query import RuleQuery
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mcmr.plugins import Table


def table(root: Path, sources: Mapping[str, str]) -> Table[ClassFact]:
    """Write one native class corpus and parse its specialized class relations."""
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[ClassFact],
    ).class_tables()


def query(
    rule: RuleContract,
    subject: Table[ClassFact],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one class rule exactly once over the repository table."""
    result = rule.invoke_table(
        subject,
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic class rule returned a model query")
    return result


def total(
    rule: RuleContract,
    subject: Table[ClassFact],
    **settings: RuleSetting,
) -> RuleValue:
    """Sum one numeric or Boolean class result across repository fact rows."""
    values = query(rule, subject, **settings).values.collect()
    for name in ("boolean_value", "integer_value", "float_value"):
        held = values.get_column(name).drop_nulls()
        if held.len():
            result = held.sum()
            if isinstance(result, bool | int | float):
                return result
    raise TypeError("the class rule emitted no numeric scalar value")


def messages(rule: RuleContract, subject: Table[ClassFact]) -> list[str]:
    """Return exact finding messages in native fact and rule order."""
    findings = query(rule, subject).findings
    if findings is None:
        return []
    return findings.rows.collect().get_column("message").to_list()
