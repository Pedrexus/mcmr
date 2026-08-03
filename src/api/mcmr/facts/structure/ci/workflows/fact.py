from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .workflow import CIWorkflow


class CIConfigurationFact(Fact):
    """Describe one continuous integration configuration."""

    workflows: list[CIWorkflow] = []
