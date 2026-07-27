from ..... import rule
from .....facts import DependencyFact
from .....models import Percentage


@rule
def dependency_evidence_gap_percentage(subject: DependencyFact) -> Percentage:
    """Measure dependencies missing facts required by offline version checks.

    Definition
    ----------
    Read `.ge4m/dependency-evidence.json` and divide dependency records missing an exact resolved
    release date, latest compatible version, or latest compatible release date by all records.
    The generated artifact, not a bundled package catalog, defines the target project's evidence.

    Evidence
    --------
    Every finding identifies the dependency, resolved version, missing fields, artifact source
    location, and any bounded refresh failures retained on the record. The percentage is zero for
    an empty dependency set because there is no missing package evidence to measure. The value is
    the percentage of dependency records missing a required fact.

    Exceptions
    ----------
    Local, VCS, private-index, and ambiguous environment resolutions can remain unknown, but their
    missing facts stay visible rather than being guessed. Projects may ignore this rule when an
    internal evidence provider owns those packages. This rule does not judge package quality,
    capability fit, or maintenance.

    Examples
    --------
    Two incomplete records among ten dependencies return `20`. A complete snapshot returns `0`.
    A network failure records the missing fields and failure source without calling the network
    during `ge4m check`.

    References
    ----------
    Cites "Python Packaging User Guide", Simple Repository API
    https://packaging.python.org/en/latest/specifications/simple-repository-api/
    Cites "PyPI API documentation", exact release metadata
    https://docs.pypi.org/api/json/
    Cites "Python Packaging User Guide", lock file specification
    https://packaging.python.org/en/latest/specifications/pylock-toml/
    """
    if not subject.dependencies:
        return 0.0
    incomplete = sum(
        dependency.resolved_release_day is None
        or not dependency.latest_compatible_version
        or dependency.latest_compatible_release_day is None
        for dependency in subject.dependencies
    )
    return incomplete / len(subject.dependencies) * 100.0
