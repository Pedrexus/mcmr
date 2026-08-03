from typing import TYPE_CHECKING

from .groups import ExportBypassFields

if TYPE_CHECKING:
    from ....foundation import SourceSpan


class ExportBypass(ExportBypassFields):
    """Retain an import that bypasses a shorter explicit package export."""

    is_cycle_safe: bool = False
    span: SourceSpan
