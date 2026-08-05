from pydantic import DirectoryPath, Field, PositiveInt

from ....domain.primitives import NonEmptyStr
from .backend import ContextBackend
from .groups import ContextualFields


class ContextualConfiguration(ContextualFields):
    """Configure the backend used after contextual execution is enabled."""

    reasoning_effort: NonEmptyStr = "medium"
    timeout_seconds: PositiveInt = 180
    minimum_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    batch_size: PositiveInt = 32


ContextualConfiguration.model_rebuild(
    _types_namespace={
        "ContextBackend": ContextBackend,
        "DirectoryPath": DirectoryPath,
        "NonEmptyStr": NonEmptyStr,
    }
)
