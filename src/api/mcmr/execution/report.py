from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import JsonValue

if TYPE_CHECKING:
    from typing import Self


class JsonReport(FrozenModel):
    """Read honest scalars out of one untrusted JSON telemetry document."""

    document: dict[str, JsonValue] = {}

    def count(self, name: str) -> int:
        """Return one nonnegative integer count, and zero for every other reported shape."""
        value = self.document.get(name)
        return value if type(value) is int and value >= 0 else 0

    def group(self, name: str) -> Self:
        """Return one nested report, or an empty report when the field is absent."""
        value = self.document.get(name)
        return type(self)(document=value) if isinstance(value, dict) else type(self)()

    def names(self) -> list[str]:
        """Return the nonblank keys this report carries in their reported order."""
        return [name for name in self.document if name.strip()]

    def text(self, name: str) -> str:
        """Return one stripped string field, or an empty string when it is absent."""
        value = self.document.get(name)
        return value.strip() if isinstance(value, str) else ""
