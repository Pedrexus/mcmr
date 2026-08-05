from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import ModuleCoupling, ModuleCouplingFact, SourceSpan
from mcmr.kernel import Kernel
from mcmr.plugins import Fact, Table
from mcmr.plugins import fact_table as in_memory_table
from mcmr.query import RuleQuery, scalar_row_value

from ...support import kernel_binary

if TYPE_CHECKING:
    from collections.abc import Sequence


def fact_table[Family: Fact](first: Family, *rest: Family) -> Table[Fact]:
    """Normalize one or more facts through a single in-memory native table."""
    subjects = (first, *rest)
    return in_memory_table(type(first), subjects)


def query(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one deterministic rule once over a retained table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic coupling rule returned a model query")
    return result


def values(result: RuleQuery) -> list[RuleValue]:
    """Return every scalar emitted by one table query in fact order."""
    return [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)]


def value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the one scalar emitted for a single retained fact."""
    answers = values(query(subject, rule, **settings))
    if len(answers) != 1:
        raise ValueError(f"expected one coupling value and received {len(answers)}")
    return answers[0]


def count_value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> int:
    """Return one integer scalar while refusing Boolean and non-count outputs."""
    answer = value(subject, rule, **settings)
    if isinstance(answer, bool) or not isinstance(answer, int):
        raise TypeError("the coupling rule did not emit an integer count")
    return answer


def count_values(result: RuleQuery) -> list[int]:
    """Return all integer scalars while refusing Boolean and non-count outputs."""
    answers = values(result)
    if any(isinstance(answer, bool) or not isinstance(answer, int) for answer in answers):
        raise TypeError("the coupling rule did not emit integer counts")
    return cast("list[int]", answers)


def coupling(module: str, *, afferent: int, efferent: int) -> ModuleCoupling:
    """Build the coupling of one module a rule reads through a dependency."""
    return ModuleCoupling(module=module, afferent_count=afferent, efferent_count=efferent)


def fact(
    *,
    module: str = "pkg.subject",
    path: str | None = None,
    afferent: int = 0,
    efferent: int = 0,
    types: int = 0,
    abstract: int = 0,
    dependencies: list[ModuleCoupling] | None = None,
) -> ModuleCouplingFact:
    """Build one module's coupling fact from the four counts the kernel states."""
    return ModuleCouplingFact(
        key=f"coupling:{module}",
        span=SourceSpan(path=path or f"{module.replace('.', '/')}.py"),
        module=module,
        afferent_count=afferent,
        efferent_count=efferent,
        declaration_count=types,
        abstract_declaration_count=abstract,
        dependencies=[] if dependencies is None else dependencies,
    )


@cache
def built(root: str) -> list[ModuleCouplingFact]:
    """Return the coupling facts this kernel builds for one repository root."""
    workspace = Kernel(binary=kernel_binary(), root=Path(root)).build(
        ["ModuleCouplingFact"], {"ModuleCouplingFact": ModuleCouplingFact}
    )
    return list(workspace.stream(ModuleCouplingFact))


def named(facts: Sequence[ModuleCouplingFact], module: str) -> ModuleCouplingFact:
    """Return one module's fact out of a stream, by the name the graph gave it."""
    return next(item for item in facts if item.module == module)
