from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .reference import DataFieldReference


class DataFieldReferenceFact(Fact):
    """Describe one resolved reference to a data field."""

    references: list[DataFieldReference] = []
