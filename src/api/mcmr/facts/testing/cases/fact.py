from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .group import TestCaseGroup
    from .loop import LiteralTestLoop


class TestCaseGroupFact(Fact):
    """Describe one related group of test cases."""

    groups: list[TestCaseGroup] = []
    loops: list[LiteralTestLoop] = []
