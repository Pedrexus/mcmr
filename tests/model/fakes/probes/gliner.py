import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import JsonValue


class GlinerProbe:
    """Return controlled native GLiNER JSON and retain the exact batch call."""

    def __init__(self, payload: Sequence[dict[str, JsonValue]]) -> None:
        self.payload = list(payload)
        self.calls: list[tuple[list[str], str, str, int]] = []

    def classify(
        self,
        texts: list[str],
        task: str,
        *,
        labels: str,
        batch_size: int,
    ) -> str:
        """Return the controlled payload in the native binding's JSON shape."""
        self.calls.append((texts, task, labels, batch_size))
        return json.dumps(self.payload)
