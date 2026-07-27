from ..... import rule
from .....facts import DataAssetFact
from .....models import Count


@rule
def data_asset_governance_gap(
    subject: DataAssetFact,
    *,
    changed_only: bool = True,
    require_domain: bool = True,
) -> Count:
    """Count governed assets missing an owner or required domain.

    Definition
    ----------
    Report each governed asset that names no owner, or that names no domain when `require_domain`
    is set. An asset with no owner has nobody to ask when its numbers look wrong and nobody to tell
    when it has to change, and a domain is what says which part of the business its numbers are
    about. Both are cheap to state at creation and expensive to reconstruct years later.

    `changed_only` keeps the default judgment on the assets this change created or modified, so a
    project adopting the rule is asked about the work in front of it rather than about its whole
    history. Setting it false measures the entire catalog, which is the baseline worth taking once.

    Evidence
    --------
    Each finding names the asset and the governance fields it leaves empty. The value is the number
    of assets missing an owner or a required domain.

    Exceptions
    ----------
    An unchanged asset is excluded by default, which is what makes the rule adoptable on a catalog
    that predates it. A domain is only required when `require_domain` says so, since some catalogs
    model that dimension elsewhere. A whitespace-only domain reads as absent on purpose, because a
    field filled with a space satisfies a schema and answers nobody.

    Examples
    --------
    A newly created asset naming a domain and no owner returns `1`. A changed asset naming both
    returns `0`. An unchanged asset naming neither returns `0` by default and `1` under
    `changed_only=False`. With `require_domain=False`, a changed asset naming an owner and no
    domain returns `0`.

    References
    ----------
    Cites "DAMA-DMBOK", data governance principles
    Cites "DataHub documentation", ownership and domain metadata
    """
    return sum(
        (not changed_only or asset.is_changed)
        and (not asset.owners or require_domain and not asset.domain.strip())
        for asset in subject.assets
    )
