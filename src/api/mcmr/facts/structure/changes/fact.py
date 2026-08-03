from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .records.record import ChangeRecord


class ChangeFact(Fact):
    """Describe source changes and their resolved approval records."""

    external_evidence = True
    changes: list[ChangeRecord] = []
