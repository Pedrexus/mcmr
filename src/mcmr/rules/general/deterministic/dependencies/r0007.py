from ..... import rule
from .....facts import DependencyFact
from .....models import Count


@rule
def explicit_dependency_state_count(
    subject: DependencyFact, *, include_yanked: bool = True
) -> Count:
    """Count dependencies with an explicit adverse upstream or release state.

    Definition
    ----------
    Read `.ge4m/dependency-evidence.json` and report only standardized PyPI project states of
    `archived`, `deprecated`, or `quarantined`, an archived source repository, and optionally an
    exact resolved release marked as yanked. Release age and repository inactivity never imply
    one of these states.

    Evidence
    --------
    Each finding retains the dependency and resolved version, every observed adverse state, the
    target lock or manifest location, and snapshot retrieval time. Unknown states remain unknown
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
    return sum(
        dependency.project_state in {"archived", "deprecated", "quarantined"}
        or dependency.is_repository_archived
        or include_yanked
        and dependency.is_resolved_release_yanked
        for dependency in subject.dependencies
    )
