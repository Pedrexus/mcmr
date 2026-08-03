from patos import FrozenModel
from pydantic import NonNegativeInt


class PythonTargetConfiguration(FrozenModel):
    """Retain the Python minor accepted by the project and configured tools."""

    project_minimum_minor: NonNegativeInt | None = None
    configured_tools: list[str] = []
    tool_target_minors: dict[str, NonNegativeInt] = {}
    per_file_target_minors: list[NonNegativeInt] = []
