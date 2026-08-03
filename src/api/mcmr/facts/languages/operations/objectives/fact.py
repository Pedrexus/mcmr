from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .service import ServiceObjective


class ServiceObjectiveFact(Fact):
    """Describe services and the objective artifacts they declare."""

    services: list[ServiceObjective] = []
