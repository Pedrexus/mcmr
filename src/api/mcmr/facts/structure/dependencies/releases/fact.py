from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .record import DependencyRecord


class DependencyFact(Fact):
    """Describe one selected dependency and its release metadata."""

    external_evidence = True
    dependencies: list[DependencyRecord] = []
