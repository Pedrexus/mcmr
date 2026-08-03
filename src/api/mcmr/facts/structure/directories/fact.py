from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from ....domain.primitives import NonEmptyStr


class DirectoryFact(Fact):
    """Describe one project directory and its unignored entries."""

    entry_count: NonNegativeInt = 0
    source_depth: NonNegativeInt = 0
    direct_file_count: NonNegativeInt = 0
    direct_directory_count: NonNegativeInt = 0
    only_child_directory: NonEmptyStr | None = None
    direct_module_count: NonNegativeInt = 0
    is_definition_catalog: bool = False
