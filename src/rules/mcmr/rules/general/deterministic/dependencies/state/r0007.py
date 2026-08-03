import polars as pl

from ...... import rule
from ......facts import DependencyFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-DEPE0002")
def explicit_dependency_state_count(
    subject: Table[DependencyFact], *, include_yanked: bool = True
) -> CountQuery:
    """Count dependencies with an explicit adverse upstream or release state.

    Definition
    ----------
    Collect current dependency evidence in memory and report only standardized project states of
    `archived`, `deprecated`, or `quarantined`, an archived source repository, and optionally an
    exact resolved release marked as yanked. Release age and repository inactivity never imply
    one of these states.

    Evidence
    --------
    Each finding retains the dependency and resolved version, every observed adverse state, the
    target lock or manifest location, and retrieval time. Unknown states remain unknown
    and produce no finding. The value is the number of dependencies carrying an adverse state.

    Exceptions
    ----------
    Set `include_yanked` to false only when another package policy owns yanked artifacts. An active
    PyPI state means uploads are allowed. It does not prove healthy maintenance. A mature package
    with old releases and no explicit adverse state is not reported by this rule.

    Examples
    --------
    A project marked `deprecated` produces one finding. A resolved yanked wheel also produces one
    finding by default. A stable parser whose latest release is three years old produces none.

    References
    ----------
    Cites "Python Packaging User Guide", Simple Repository API project status markers
    https://packaging.python.org/en/latest/specifications/project-status-markers/
    Cites "Python Packaging User Guide", Simple Repository API yanked files
    https://packaging.python.org/en/latest/specifications/file-yanking/
    Cites "GitHub documentation", repository archived field
    https://docs.github.com/en/rest/repos/repos
    """
    relations = subject
    selected = relations.records("dependencies").filter(
        pl.col("project_state").is_in(["archived", "deprecated", "quarantined"])
        | (pl.col("repository_state") == "archived")
        | (pl.lit(include_yanked) & (pl.col("resolved_release_state") == "yanked"))
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "explicit dependency state count",
            evidence=pl.col("evidence"),
        ),
    )
