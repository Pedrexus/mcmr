from ..... import rule
from .....facts import RouteFact
from .....models import Count


@rule
def inconsistent_route_path_style(subject: RouteFact) -> Count:
    """Count route segments spelled against the convention the rest of the paths follow.

    Definition
    ----------
    Read every path segment this repository declares, decide which word separator the majority use,
    and report a segment that uses the other one. A URL is an interface a caller types, and one
    that answers at `/user-profiles` but not at `/user_profiles` fails in a way that looks like an
    outage rather than a typo. The convention itself does not matter, and holding one does.

    Evidence
    --------
    Each finding names the path, the segment, and the separator the repository otherwise uses. The
    value is the number of segments spelled against it.

    Exceptions
    ----------
    A parameter segment is skipped, because it names a variable rather than a word a caller types.
    A repository with no separated segment at all has no convention to break and returns nothing.
    A path that has to match an external specification keeps that specification's spelling, which
    is a reason to exclude the module rather than to change the path.

    Examples
    --------
    Where `/user-profiles` and `/order-items` are declared, a `/audit_log` returns `1`. Where every
    path is one word, nothing is reported, because nothing has been decided yet.

    References
    ----------
    Cites "Google API Design Guide", resource naming
    https://cloud.google.com/apis/design/resource_names
    Cites "Microsoft REST API Guidelines", URL structure
    https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md
    Cites "Architectural Styles and the Design of Network-based Software Architectures"
    """
    segments = [
        segment
        for route in subject.routes
        for segment in route.path.split("/")
        if segment and "{" not in segment
    ]
    hyphenated = sum("-" in segment for segment in segments)
    underscored = sum("_" in segment for segment in segments)
    if not hyphenated or not underscored:
        return 0
    return min(hyphenated, underscored)
