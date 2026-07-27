from ..... import rule
from .....facts import WaiverFact
from .....models import Count


@rule
def waiver_debt(
    subject: WaiverFact,
    *,
    required_metadata: tuple[str, ...] = ("reason",),
    maximum_age_days: int = 90,
    exclude: tuple[str, ...] = (
        ".benchmarks/",
        ".chefe/",
        ".git/",
        ".venv/",
        "__pycache__/",
        "_build/",
        "build/",
        "dist/",
        "venv/",
    ),
) -> Count:
    """Count quality waivers that lack a current bounded justification.

    Definition
    ----------
    Count inline lint, typing, coverage, security, architecture, and MCMR suppressions that are
    expired, older than the configured age, overly broad, missing a creation date, or missing
    configured metadata. The rule judges waiver hygiene rather than repeating the diagnostic. A
    waiver justifies itself where it is written, so its age comes from a `since` field and its
    expiry from an `expires` field, each written as an ISO date on the suppression line itself.

    Evidence
    --------
    Findings retain the waiver kind, scope, available structured metadata, age problem, and source
    location. Metadata is a run of `key=value` fields written after the marker, each value running
    to the next field name, so a reason may hold spaces without being quoted.

    Exceptions
    ----------
    Permanent third-party compatibility gaps may remain when narrowly scoped and supported by a
    current upstream reference. Generated or synthetic trees can be omitted through `exclude`.
    `required_metadata` names the fields a suppression comment has to carry, defaulting to a
    reason, and `maximum_age_days` is how long one may live before it counts as debt.

    Examples
    --------
    Two blanket ignores and one expired security waiver produce `3`. A narrow, dated suppression
    with a reason does not count. A permanent compatibility waiver also needs an upstream URL.

    References
    ----------
    Generalizes Ruff PGH004 blanket-noqa
    Generalizes Ruff PGH003 blanket-type-ignore
    Cites "OpenSSF Scorecard", dangerous workflow and token permission checks
    """
    return sum(
        not any(part in waiver.location for part in exclude)
        and (
            waiver.age_days is None
            or waiver.age_days > maximum_age_days
            or waiver.expires_in_days is not None
            and waiver.expires_in_days < 0
            or waiver.is_overly_broad
            or any(not waiver.metadata.get(field, "").strip() for field in required_metadata)
        )
        for waiver in subject.waivers
    )
