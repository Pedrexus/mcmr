from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from pydantic import TypeAdapter

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import FileHistory, HistoryChange, RepositoryHistoryFact, SourceSpan
from mcmr.plugins import fact_table
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.table import HistoryRelations

if TYPE_CHECKING:
    from collections.abc import Sequence

_FIXTURES = Path(__file__).parents[1] / "fixtures"


class CouplingRow(TypedDict):
    """Type one co-change row returned by the history relation."""

    left: str
    right: str
    shared_commit_count: int
    left_commit_count: int
    right_commit_count: int
    import_reference_count: int


def query(
    rule: RuleContract,
    subject: RepositoryHistoryFact,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one history rule once and keep everything it reported."""
    table = fact_table(RepositoryHistoryFact, [subject])
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic history rule returned a model query")
    return result


def value(
    rule: RuleContract,
    subject: RepositoryHistoryFact,
    **settings: RuleSetting,
) -> RuleValue:
    """Invoke one history rule once over one in-memory repository fact."""
    return scalar_frame_value(query(rule, subject, **settings).values.collect())


def pairs(subject: RepositoryHistoryFact, maximum_commit_files: int = 30) -> list[CouplingRow]:
    """Return the relational co-change rows a history rule reads."""
    rows = HistoryRelations(fact_table(RepositoryHistoryFact, [subject])).coupling(
        maximum_commit_files
    )
    return cast("list[CouplingRow]", rows.collect().to_dicts())


def record(
    path: str,
    *,
    commits: int = 1,
    authors: int = 1,
    days: int = 0,
    lines: int = 0,
    is_test: bool = False,
    imports: tuple[str, ...] = (),
) -> FileHistory:
    """Build one file's history."""
    return FileHistory(
        path=path,
        author_count=authors,
        additional_commit_count=commits - authors,
        days_since_last_change=days,
        line_count=lines,
        is_test=is_test,
        imports=list(imports),
    )


def change(*paths: str, width: int | None = None) -> HistoryChange:
    """Build one commit carrying these requested paths."""
    return HistoryChange(
        other_file_count=(width or len(paths)) - len(paths),
        paths=list(paths),
    )


def coupled(
    left: str,
    *,
    right: str,
    shared: int = 5,
    counts: Sequence[int] = (5, 5),
) -> list[HistoryChange]:
    """Build commits that give one pair exact support and side counts."""
    return [
        *[change(left, right) for _ in range(shared)],
        *[change(left) for _ in range(counts[0] - shared)],
        *[change(right) for _ in range(counts[1] - shared)],
    ]


def history(
    *, files: Sequence[FileHistory] = (), changes: Sequence[HistoryChange] = ()
) -> RepositoryHistoryFact:
    """Build the one fact carrying everything the log said."""
    return RepositoryHistoryFact(
        key="history",
        span=SourceSpan(path=""),
        unscoped_commit_count=(
            max(len(changes), *(record.commit_count for record in files), 0) - len(changes)
        ),
        files=list(files),
        changes=list(changes),
    )


@cache
def hotspots() -> list[tuple[str, int]]:
    """Read the Archy hotspot result frozen at commit `408679b`."""
    return TypeAdapter(list[tuple[str, int]]).validate_json(
        (_FIXTURES / "archy-408679b-hotspots.json").read_text()
    )


@cache
def mined() -> RepositoryHistoryFact:
    """Read the MCMR history fact frozen beside the independent oracle result."""
    return RepositoryHistoryFact.model_validate_json(
        (_FIXTURES / "archy-408679b-history.json").read_text()
    )


@cache
def coupling() -> list[tuple[str, str, int, int, int]]:
    """Read the Archy coupling result frozen at commit `408679b`."""
    return TypeAdapter(list[tuple[str, str, int, int, int]]).validate_json(
        (_FIXTURES / "archy-408679b-coupling.json").read_text()
    )
