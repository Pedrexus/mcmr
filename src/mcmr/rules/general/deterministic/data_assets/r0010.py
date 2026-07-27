from ..... import rule
from .....facts import LineageEdgeFact
from .....models import Count


@rule
def unresolved_lineage_endpoint(subject: LineageEdgeFact) -> Count:
    """Count lineage edges whose endpoint is absent from the catalog snapshot.

    Definition
    ----------
    Resolve both endpoints of every directed lineage edge against the asset index and count each
    endpoint that resolves to nothing, so one edge naming two unknown assets counts twice. Lineage
    is what the impact and health rules walk, and an edge with a dangling endpoint means the graph
    they walk is incomplete in a way that quietly shrinks every answer built on it.

    Reading this first is the point. A low impact count over a broken graph looks exactly like a
    low impact count over a healthy one, and only this rule tells the two apart.

    Evidence
    --------
    Each finding names the edge, which side of it failed to resolve, and the identifier that
    resolved to nothing. The value is the number of unresolved endpoints across every edge.

    Exceptions
    ----------
    An edge whose two endpoints are both cataloged contributes nothing, however stale either asset
    is, because this rule judges snapshot integrity rather than asset health. An asset reachable
    only through an edge the snapshot never recorded is invisible here, so this reports the
    incompleteness it can see rather than proving the graph complete.

    Examples
    --------
    An edge from a cataloged `raw` to an uncataloged `report` returns `1`. An edge whose source and
    target are both uncataloged returns `2`. An edge between two cataloged assets returns `0`.

    References
    ----------
    Cites "OpenLineage specification", object model
    Cites "W3C PROV Data Model"
    """
    return sum(
        not endpoint_exists
        for edge in subject.edges
        for endpoint_exists in (edge.source_exists, edge.target_exists)
    )
