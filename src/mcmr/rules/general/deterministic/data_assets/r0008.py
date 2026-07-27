from ..... import rule
from .....facts import DataChangeFact
from .....models import Percentage


@rule
def data_change_test_gap_percentage(subject: DataChangeFact) -> Percentage:
    """Measure impacted downstream assets lacking retained test evidence.

    Definition
    ----------
    Build the impacted set of every breaking change, which is the changed asset together with every
    asset downstream of it, then divide the impacted pairs the change's own test evidence does not
    name by every impacted pair. The result is the share of the blast radius nobody checked, so it
    answers the question a raw impact count leaves open, which is whether anyone looked.

    Test evidence is what the change itself retains rather than what a suite happens to cover,
    because a passing suite that never touches the changed column proves nothing about the change.

    Evidence
    --------
    Each finding names one impacted asset that no retained test evidence covers. The value is the
    percentage of impacted pairs with no test evidence, and it is zero when nothing breaking exists
    to be impacted.

    Exceptions
    ----------
    A nonbreaking change contributes nothing to either side, so a snapshot holding only additive
    changes measures zero rather than a full gap. A snapshot with no breaking change at all
    measures zero for the same reason, since a share of an empty set has no meaning. The changed
    asset counts as impacted by its own change, so covering only its consumers still leaves a gap,
    which is deliberate because the changed asset is the one thing that certainly moved.

    Examples
    --------
    A breaking change to `orders`, whose lineage records `dashboard` and `invoice`, has three
    impacted pairs. Test evidence naming `orders` and `dashboard` leaves one uncovered, so the
    value is about `33.3`. Evidence naming all three returns `0`, and evidence naming none returns
    `100`. A change marked nonbreaking returns `0` whatever its lineage holds.

    References
    ----------
    Cites "The Google Testing Blog", change impact and test selection
    """
    impacted = {
        (change.asset_identifier, affected)
        for change in subject.changes
        if change.is_breaking
        for affected in {change.asset_identifier, *change.downstream_assets}
    }
    if not impacted:
        return 0.0
    tested = {
        (change.asset_identifier, affected)
        for change in subject.changes
        if change.is_breaking
        for affected in change.tested_assets
    }
    return len(impacted - tested) / len(impacted) * 100.0
