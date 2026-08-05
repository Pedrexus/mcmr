from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .context import PublicationContext


@runtime_checkable
class ResultPublisher(Protocol):
    """Write one completed run back to the system that supplied its external evidence.

    A provider opts in by implementing this beside `FactProvider`. Publication is never part of
    reading evidence, so no analysis path can reach it. Only the explicit writeback command does,
    and it hands over the assets a run actually judged rather than the whole catalog.
    """

    async def publish(self, context: PublicationContext) -> list[str]: ...
