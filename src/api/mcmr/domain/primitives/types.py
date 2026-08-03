from typing import Annotated, Protocol, runtime_checkable

from annotated_types import Predicate
from pydantic import Field, JsonValue, StringConstraints


@runtime_checkable
class JsonTransport(Protocol):
    """Fetch one JSON value through a bounded asynchronous boundary."""

    async def get(self, url: str, *, accept: str = "application/json") -> JsonValue: ...


type NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


type EvidenceIds = Annotated[
    list[NonEmptyStr],
    Field(min_length=1, max_length=8),
    Predicate(lambda values: len(values) == len(set(values))),
]
