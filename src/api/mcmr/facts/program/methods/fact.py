from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .group import MethodCloneGroup


class MethodGroupFact(Fact):
    """Describe one related group of methods."""

    groups: list[MethodCloneGroup] = []
