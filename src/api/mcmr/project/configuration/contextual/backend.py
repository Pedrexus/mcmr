from enum import StrEnum, auto


class ContextBackend(StrEnum):
    """Name one interchangeable contextual classification implementation."""

    GLINER2 = auto()
    CODEX = auto()
    CLAUDE = auto()
    OPENROUTER = auto()
