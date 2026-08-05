from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .change import DataChange


class DataChangeFact(Fact):
    """Describe one schema or contract change affecting data."""

    external_evidence = True
    changes: list[DataChange] = []
