from ..... import rule
from .....facts import DataChangeFact
from .....models import Count


@rule
def breaking_data_change_impact(subject: DataChangeFact) -> Count:
    """Count downstream assets exposed to declared breaking schema changes.

    Definition
    ----------
    Take every change a provider declares breaking, which is a removed field or an incompatible
    type change, and count the distinct asset pairs it reaches through the supplied lineage graph.
    The changed asset counts as reached by its own change, since whatever reads it directly is
    affected first, and each transitive consumer counts once however many paths lead to it.

    This is a blast radius rather than a verdict. It says how many places have to be looked at
    before the change ships, and a large number is a reason to stage the change rather than proof
    that anything is broken.

    Evidence
    --------
    Each finding names the changed asset, one downstream asset reached from it, and the change
    facts that made it breaking. The value is the number of distinct changed asset and reached
    asset pairs.

    Exceptions
    ----------
    A change the provider does not mark breaking contributes nothing, so adding a nullable field
    reaches no one. A pair reached twice through two lineage paths is counted once, because a
    consumer is one place to look however many routes lead to it. A consumer the lineage graph does
    not record is invisible here, which is why an empty lineage graph reduces every change to its
    own asset alone rather than to zero.

    Examples
    --------
    Removing a field from `orders`, whose lineage records `dashboard` and `invoice` downstream,
    returns `3`, which is `orders` itself plus its two consumers. The same removal on an asset with
    three distinct consumers returns `4` for the same reason. A breaking change to an asset with no
    recorded consumers returns `1`, and adding a nullable field returns `0`.

    References
    ----------
    Cites "OpenLineage specification", lineage model
    Cites "Apache Avro specification"
    """
    pairs = {
        (change.asset_identifier, affected)
        for change in subject.changes
        if change.is_breaking
        for affected in {change.asset_identifier, *change.downstream_assets}
    }
    return len(pairs)
