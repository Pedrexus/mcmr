from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .check import CICheck


class CICheckFact(Fact):
    """Describe one check executed by continuous integration."""

    external_evidence = True
    checks: list[CICheck] = []
