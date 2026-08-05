from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .asset import DataAsset


class DataAssetFact(Fact):
    """Describe one governed data asset."""

    external_evidence = True
    assets: list[DataAsset] = []
