from patos import FrozenModel
from pydantic import DirectoryPath

from ....domain.primitives import NonEmptyStr
from .backend import ContextBackend


class ContextualFields(FrozenModel):
    """Retain contextual backend, binary, model, and local model path."""

    backend: ContextBackend = ContextBackend.CODEX
    binary: NonEmptyStr = "codex"
    model: NonEmptyStr = "gpt-5.6-terra"
    model_path: DirectoryPath | None = None
