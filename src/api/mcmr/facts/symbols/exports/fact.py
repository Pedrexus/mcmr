from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .entries.bypass import ExportBypass
    from .entries.public import PublicExport


class ExportFact(Fact):
    """Describe one explicit public name and its repository consumers."""

    public_export: PublicExport
    bypasses: list[ExportBypass] = []
