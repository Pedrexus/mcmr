import json
from typing import TYPE_CHECKING

import httpx
from pydantic import JsonValue, TypeAdapter

if TYPE_CHECKING:
    from pathlib import Path

_exchanges = TypeAdapter(list[dict[str, JsonValue]])


class RecordedTransport(httpx.AsyncBaseTransport):
    """Replay captured DataHub GraphQL exchanges so a checkout needs no running service.

    One JSON file per operation holds the exchanges that operation produced, each pairing the
    request variables with the exact response envelope the server returned. A live capture appends
    the envelope verbatim, so re-recording against a real endpoint is a file swap rather than a
    format change.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Answer one request from the recording that names its operation and variables."""
        payload = TypeAdapter(dict[str, JsonValue]).validate_python(json.loads(request.content))
        operation = payload["operationName"]
        if not isinstance(operation, str):
            raise RuntimeError("a recorded DataHub request must name one operation")
        return httpx.Response(200, json=self._answer(operation, payload.get("variables")))

    def _answer(self, operation: str, variables: JsonValue) -> JsonValue:
        """Return the envelope recorded for exactly these variables."""
        path = self.root / f"{operation}.json"
        if not path.is_file():
            raise RuntimeError(f"the DataHub recording holds no operation {operation}")
        exchanges = _exchanges.validate_python(json.loads(path.read_text(encoding="utf-8")))
        for exchange in exchanges:
            if exchange["variables"] == variables:
                return exchange["response"]
        raise RuntimeError(f"the DataHub recording of {operation} holds no {variables}")
