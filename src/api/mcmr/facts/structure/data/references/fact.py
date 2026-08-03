from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .reference import DataAssetReference


class DataAssetReferenceFact(Fact):
    """Describe one resolved reference to a governed data asset."""

    references: list[DataAssetReference] = []
