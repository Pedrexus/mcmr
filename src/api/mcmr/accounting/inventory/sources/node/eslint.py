from ..base import NodeRegistry


class ESLintRegistry(NodeRegistry):
    """Read the rules ESLint itself ships."""

    tool = "eslint"
