from .base import InventorySource
from .command.clippy import ClippyRegistry
from .command.ruff import RuffRegistry
from .native import ClangTidyRegistry, CppcheckRegistry
from .node import ESLintRegistry, TypeScriptESLintRegistry
from .pylint.registry import PylintRegistry

_BUILTIN_SOURCE_TYPES = (
    ClangTidyRegistry,
    ClippyRegistry,
    CppcheckRegistry,
    ESLintRegistry,
    PylintRegistry,
    RuffRegistry,
    TypeScriptESLintRegistry,
)

__all__ = ["InventorySource"]
