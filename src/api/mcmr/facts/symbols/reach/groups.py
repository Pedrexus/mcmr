from typing import Literal

from patos import FrozenModel
from pydantic import NonNegativeInt

from ...foundation import SourceSpan, Visibility


class SymbolReachFields:
    """Group flat reach fields by declaration, spread, and operation."""

    class Declaration(FrozenModel):
        """Retain declaration identity, visibility, scope, and local references."""

        qualname: str
        kind: Literal["class", "function", "method", "property", "variable", "attribute"]
        span: SourceSpan
        visibility: Visibility = Visibility.PUBLIC
        is_module_scope: bool = False
        is_decorated: bool = False
        own_file_references: NonNegativeInt = 0

    class Spread(Declaration):
        """Retain cross-file spread and resolved operation counts."""

        other_file_references: NonNegativeInt = 0
        referencing_files: NonNegativeInt = 0
        referencing_directories: NonNegativeInt = 0
        referencing_packages: NonNegativeInt = 0
        call_count: NonNegativeInt = 0
        instantiate_count: NonNegativeInt = 0
        inherit_count: NonNegativeInt = 0

    class Operations(Spread):
        """Retain import operations reaching the declaration."""

        import_count: NonNegativeInt = 0
