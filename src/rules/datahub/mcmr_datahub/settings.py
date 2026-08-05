from os import environ
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import AnyHttpUrl, JsonValue, PositiveFloat, TypeAdapter

from mcmr.plugins import NonEmptyStr

from .request import DataHubCatalogRequest

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Self

# The server a replayed run reports, so a recorded checkout needs no environment at all.
_RECORDED_SERVER = "http://recorded.invalid"

# The flat option names a project writes, folded into the request they all describe.
_REQUEST = ("query", "page_size", "max_assets", "since")


class DataHubSettings(FrozenModel):
    """Validate one stateless DataHub connection and bounded catalog request."""

    server: AnyHttpUrl
    sql_dialect: str = ""
    timeout_seconds: PositiveFloat = 30.0
    recorded: str = ""
    report_url: str = ""
    catalog: DataHubCatalogRequest = DataHubCatalogRequest()

    @property
    def token(self) -> NonEmptyStr | None:
        """Read an optional bearer token only when the provider is about to connect."""
        return (
            TypeAdapter(NonEmptyStr).validate_python(value)
            if (value := environ.get("DATAHUB_GMS_TOKEN")) is not None
            else None
        )

    @classmethod
    def from_mapping(cls, settings: Mapping[str, JsonValue]) -> Self:
        """Read public options from MCMR config and the server URL from the environment."""
        configured = dict(settings)
        recorded = configured.get("recorded")
        fallback = _RECORDED_SERVER if isinstance(recorded, str) and recorded.strip() else None
        server = configured.get("server", environ.get("DATAHUB_GMS_URL", fallback))
        if not isinstance(server, str) or not server.strip():
            raise ValueError(
                "DataHub external rules require `server` in MCMR settings or DATAHUB_GMS_URL"
            )
        configured["server"] = server
        configured["catalog"] = {
            name: configured.pop(name) for name in _REQUEST if name in configured
        }
        return cls.model_validate(configured)
