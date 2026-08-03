import urllib.request
from functools import partial

from anyio.to_thread import run_sync
from patos import FrozenModel
from pydantic import Field, JsonValue, PositiveInt, TypeAdapter


class UrlJsonTransport(FrozenModel):
    """Use the standard library HTTP client without blocking the event loop."""

    timeout_seconds: PositiveInt = 30
    github_token: str = Field(default="", exclude=True, repr=False)

    async def get(self, url: str, *, accept: str = "application/json") -> JsonValue:
        """Fetch and decode one JSON document in a worker thread."""
        return await run_sync(partial(self.read, url, accept=accept))

    def read(self, url: str, *, accept: str) -> JsonValue:
        """Perform one bounded request and validate its JSON value."""
        headers = {"Accept": accept, "User-Agent": "mcmr-dependency-evidence"}
        if self.github_token and url.startswith("https://api.github.com/"):
            headers["Authorization"] = f"Bearer {self.github_token}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return TypeAdapter(JsonValue).validate_json(response.read())
