from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .assignment import ConfigurationAssignment
    from .python import PythonTargetConfiguration


class ProjectConfigurationFact(Fact):
    """Describe one project configuration source."""

    assignments: list[ConfigurationAssignment] = []
    python_target: PythonTargetConfiguration | None = None
