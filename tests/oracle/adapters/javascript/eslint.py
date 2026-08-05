import json
import shutil
from pathlib import Path

from ...contracts import Diagnostic
from ..base import Oracle


class ESLintOracle(Oracle):
    """Read what ESLint reports for a chosen set of its rules, out of its own JSON formatter.

    ESLint wants two things before it will answer at all and both are facts about the tool rather
    than about the source. It resolves a flat configuration and every plugin that configuration
    names through Node's own module lookup, so the tree is given a `node_modules` pointing at the
    installation the binary came from and a configuration written beside it. A rule is spelled the
    way ESLint spells it, so a `typescript-eslint` rule arrives under its `@typescript-eslint`
    prefix and is enabled through the plugin rather than through a second tool.
    """

    tool = "eslint"
    binary = "eslint"

    ceiling: int | None = None

    def configure(self, root: Path) -> None:
        """Write the flat configuration and link the packages it imports into the tree."""
        linked = root / "node_modules"
        if not linked.exists():
            linked.symlink_to(self.packages(), target_is_directory=True)
        allowance = "" if self.ceiling is None else f', {{ "max": {self.ceiling} }}'
        enabled = ",\n    ".join(f'"{name}": ["error"{allowance}]' for name in self.rules)
        (root / "eslint.config.mjs").write_text(
            "import tseslint from 'typescript-eslint';\n"
            "export default [\n"
            "  { languageOptions: { ecmaVersion: 'latest', sourceType: 'module' } },\n"
            "  { files: ['**/*.ts'], languageOptions: { parser: tseslint.parser } },\n"
            "  { plugins: { '@typescript-eslint': tseslint.plugin } },\n"
            f"  {{ rules: {{\n    {enabled}\n  }} }},\n"
            "];\n"
        )

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every message ESLint reported for the chosen rules."""
        self.configure(root)
        completed = self.ran(
            ["eslint", "--no-config-lookup", "--config", "eslint.config.mjs", "--format", "json"],
            root,
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=item["filePath"],
                line=message["line"],
                rule=message["ruleId"],
                detail=message["message"],
            )
            for item in json.loads(completed.stdout or "[]")
            for message in item["messages"]
            if message["ruleId"] in wanted
        ]

    def packages(self) -> Path:
        """Return the `node_modules` directory the installed ESLint was resolved out of."""
        found = shutil.which(self.binary)
        if found is None:
            raise FileNotFoundError("eslint is not installed")
        located = next(
            (parent for parent in Path(found).resolve().parents if parent.name == "node_modules"),
            None,
        )
        if located is None:
            raise FileNotFoundError(f"{found} sits outside any node_modules directory")
        return located
