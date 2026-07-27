from pydantic import BaseModel, ConfigDict


class FrozenFlexModel(BaseModel):
    """Keep validated models immutable while accepting provider-specific fact fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class FrozenRootModel(FrozenFlexModel):
    """Share frozen configuration for concrete single-value models."""
