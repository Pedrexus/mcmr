from typing import TYPE_CHECKING

from patos import FrozenModel

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import SourceSpan
from mcmr.plugins import Fact
from mcmr.query import RuleQuery, scalar_frame_value

from ...support import retained_query

if TYPE_CHECKING:
    from mcmr.plugins import Table

    from ...support import Declared


class QueryAnswer(FrozenModel):
    """Expose one retained table result with its relational evidence."""

    value: RuleValue
    query: RuleQuery


def answer(
    rule: RuleContract,
    subject: Fact,
    **settings: RuleSetting,
) -> QueryAnswer:
    """Execute one generic rule exactly once over one retained fact."""
    result = retained_query(subject, rule, **settings)
    return QueryAnswer(value=scalar_frame_value(result.values.collect()), query=result)


def fact[FactT: Fact](family: type[FactT], **records: Declared) -> FactT:
    """Return one located fact of the requested family."""
    return family.model_validate(
        {"key": family.__name__, "span": SourceSpan(path="project")} | records
    )


def native_query[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one specialized rule once over its complete native table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic native rule returned a model query")
    return result
