from typing import TYPE_CHECKING

from ...foundation import Fact, NodeRef

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class ImportBindingFields:
    """Group flat import fields by identity, role, and visibility."""

    class Identity(Fact):
        """Retain imported and bound names."""

        name: str
        module: str
        imported_name: str = ""
        importer_module: str = ""

    class Source(Identity):
        """Retain exact source nodes and the number of qualifying reads."""

        declaration: NodeRef | None = None
        binding: NodeRef | None = None
        module_node: NodeRef | None = None
        references: list[NodeRef] = []
        relative_level: NonNegativeInt = 0
        reference_count: NonNegativeInt = 0

    class Role(Source):
        """Retain qualifying use, external, export, type, and ownership roles."""

        has_qualifying_use: bool = False
        is_external: bool = False
        is_reexported: bool = False
        is_type_only: bool = False
        has_documented_side_effect: bool = False
        is_relative: bool = False
        is_project_owned: bool = False

    class Visibility(Role):
        """Retain sole binding, private component, and wildcard evidence."""

        is_sole_binding: bool = False
        has_private_module_component: bool = False
        is_private_member: bool = False
        is_private_uppercase_constant: bool = False
        is_wildcard: bool = False
