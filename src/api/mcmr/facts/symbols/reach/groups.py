from typing import TYPE_CHECKING, Literal

from patos import FrozenModel

from ...foundation import SourceSpan, Visibility

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class SymbolReachFields:
    """Group flat reach fields by declaration, spread, and operation."""

    class Identity(FrozenModel):
        """Retain declaration identity and stated visibility."""

        qualname: str
        kind: Literal["class", "function", "method", "property", "variable", "attribute"]
        span: SourceSpan
        visibility: Visibility = Visibility.PUBLIC

    class Declaration(Identity):
        """Retain owner contract, scope, and local references."""

        owner_visibility: Visibility = Visibility.PUBLIC
        owner_has_inheritance: bool = False
        is_module_scope: bool = False
        is_decorated: bool = False
        own_file_references: NonNegativeInt = 0

    class Ownership(Declaration):
        """Retain cross-file and owner resolution completeness."""

        other_file_references: NonNegativeInt = 0
        owner_references: NonNegativeInt = 0
        non_owner_references: NonNegativeInt = 0
        unresolved_name_references: NonNegativeInt = 0

    class Spread(Ownership):
        """Retain repository spread and resolved operation counts."""

        referencing_files: NonNegativeInt = 0
        referencing_directories: NonNegativeInt = 0
        referencing_packages: NonNegativeInt = 0
        call_count: NonNegativeInt = 0
        instantiate_count: NonNegativeInt = 0
        inherit_count: NonNegativeInt = 0

    class Operations(Spread):
        """Retain import operations reaching the declaration."""

        import_count: NonNegativeInt = 0
