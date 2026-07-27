from ..... import rule
from .....facts import DependencyFact
from .....models import Percentage


@rule
def dependency_technical_lag(
    subject: DependencyFact,
    *,
    maximum_release_lag_days: int = 180,
    include_development: bool = False,
) -> Percentage:
    """Measure resolved dependencies lagging their latest compatible release.

    Definition
    ----------
    Read `.ge4m/dependency-evidence.json` and compare exact release timestamps. Divide in-scope
    dependencies whose latest compatible release is more than `maximum_release_lag_days` newer
    than the resolved release by all in-scope dependencies with complete timestamp evidence.

    Evidence
    --------
    Findings retain the declared requirement, exact resolved and compatible versions, resolved
    version age, release lag, artifact location, and stable evidence identifiers. Missing upstream
    facts remain explicit snapshot failures and do not become maintenance conclusions. The value is
    the percentage of measurable dependencies lagging past the configured window.

    Exceptions
    ----------
    The comparison uses the latest release compatible with the declared requirement. Local, VCS, or
    otherwise unresolved dependencies remain outside the denominator until evidence is known.
    Package maintenance, archival, and deprecation are separate observations. Development
    dependencies stay out of both sides unless `include_development` asks for them, since a lagging
    test tool and a lagging runtime dependency carry very different risk.

    Examples
    --------
    Four dependencies beyond the configured lag among forty measurable dependencies produce `10`.
    A year-old resolved release matching the latest compatible release does not count as lag.

    References
    ----------
    Cites "PyPI API documentation", release upload timestamps
    https://docs.pypi.org/api/json/
    Cites "Python Packaging User Guide", dependency specification
    https://packaging.python.org/specifications/declaring-project-metadata/
    """
    complete = [
        dependency
        for dependency in subject.dependencies
        if (include_development or not dependency.is_development)
        and dependency.resolved_release_day is not None
        and dependency.latest_compatible_release_day is not None
    ]
    if not complete:
        return 0.0
    lagging = sum(
        dependency.latest_compatible_release_day - dependency.resolved_release_day
        > maximum_release_lag_days
        for dependency in complete
        if dependency.latest_compatible_release_day is not None
        and dependency.resolved_release_day is not None
    )
    return lagging / len(complete) * 100.0
