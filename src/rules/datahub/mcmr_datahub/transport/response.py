from patos import FrozenModel
from pydantic import Field, JsonValue


class GraphQLResponse(FrozenModel):
    """Validate the standard DataHub GraphQL response envelope."""

    data: dict[str, JsonValue] | None = None
    errors: list[dict[str, JsonValue]] = Field(default_factory=list)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)
