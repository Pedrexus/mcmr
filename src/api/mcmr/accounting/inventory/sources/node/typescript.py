from ..base import NodeRegistry


class TypeScriptESLintRegistry(NodeRegistry):
    """Read the rules the typescript-eslint plugin ships."""

    tool = "typescript-eslint"
