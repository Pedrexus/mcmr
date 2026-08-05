from typing import TYPE_CHECKING

import httpx

from .response import GraphQLResponse

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from pydantic import JsonValue

    from mcmr.plugins import NonEmptyStr

    from ..settings import DataHubSettings


class DataHubGraphQL:
    """Execute bounded direct GraphQL requests without a local service or cache."""

    def __init__(
        self,
        settings: DataHubSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        """Open one reusable connection pool for the provider request."""
        headers = (
            {"Authorization": f"Bearer {token}"}
            if (token := self.settings.token) is not None
            else {}
        )
        self.client = httpx.AsyncClient(
            base_url=f"{str(self.settings.server).rstrip('/')}/",
            headers=headers,
            timeout=self.settings.timeout_seconds,
            transport=self.transport,
        )
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the request-local connection pool."""
        if self.client is not None:
            await self.client.aclose()
        self.client = None

    async def execute(
        self,
        query: NonEmptyStr,
        variables: dict[str, JsonValue],
        operation: NonEmptyStr,
    ) -> dict[str, JsonValue]:
        """Return validated GraphQL data or fail with the server errors."""
        if self.client is None:
            raise RuntimeError("DataHub GraphQL client must be opened before use")
        response = await self.client.post(
            "api/graphql",
            json={"query": query, "variables": variables, "operationName": operation},
        )
        response.raise_for_status()
        envelope = GraphQLResponse.model_validate(response.json())
        if envelope.errors:
            raise RuntimeError(f"DataHub GraphQL request failed with {envelope.errors}")
        if envelope.data is None:
            raise RuntimeError("DataHub GraphQL response omitted data")
        return envelope.data
