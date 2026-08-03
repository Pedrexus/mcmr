from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .analysis import EnumAnalysis
    from .context.file import EnumFile
    from .context.scope import EnumScope


class Enum(Fact):
    """Describe enumerations, their members, scopes, and files."""

    enums: list[EnumAnalysis] = []
    scopes: list[EnumScope] = []
    files: list[EnumFile] = []
