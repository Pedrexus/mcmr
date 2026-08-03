from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from pathspec import GitIgnoreSpec
from patos import FrozenModel, Runtime

from ...domain.contracts import OutputContract, RuleContract, RuleScope, RuleSetting
from ...rulebook.catalog import Catalog

if TYPE_CHECKING:
    from ...facts import Fact
    from ...table import RepositoryTables


class PreparedRule(FrozenModel):
    """Hold every invariant input one rule needs for its single table invocation."""

    rule: Runtime[RuleContract]
    path: str
    scope: RuleScope
    contract: OutputContract
    settings: Mapping[str, RuleSetting]
    exclusion_spec: Runtime[GitIgnoreSpec]

    @property
    def families(self) -> set[type[Fact]]:
        """Return every repository table this rule requires."""
        return {family for _, family in self.rule.tables}

    @property
    def primary_family(self) -> type[Fact]:
        """Return the table family whose identities the query must answer for."""
        return self.rule.primary_family

    @property
    def table_languages(self) -> dict[str, set[str]]:
        """Resolve automatic path scope beside annotated table constraints."""
        return Catalog.languages(self.path, self.scope, self.rule.table_languages)

    @classmethod
    def of(
        cls,
        rule: RuleContract,
        contract: OutputContract,
        settings: Mapping[str, RuleSetting],
        exclusions: Sequence[str],
    ) -> PreparedRule:
        """Compile one selected rule and its invariant runtime inputs."""
        return cls(
            rule=rule,
            path=rule.callable_path,
            scope=Catalog.identity(rule.module, rule.id)[0],
            contract=contract,
            settings=settings,
            exclusion_spec=GitIgnoreSpec.from_lines(exclusions),
        )

    def accepts_path(self, path: str) -> bool:
        """Whether source exclusions let one discovered path reach this rule."""
        return not self.exclusion_spec.match_file(path)

    def applies_to(self, tables: RepositoryTables) -> bool:
        """Whether every constrained dependency has rows in a supported language."""
        return all(
            not (languages := self.table_languages[name])
            or bool(languages & tables[family].observed_languages)
            for name, family in self.rule.tables
        )

    def boolean_setting(self, name: str, *, default: bool) -> bool:
        """Return one Boolean setting after the configuration boundary validated it."""
        value = self.settings.get(name, default)
        if not isinstance(value, bool):
            raise TypeError(f"setting {name} is not Boolean")
        return value

    def integer_setting(self, name: str, default: int) -> int:
        """Return one integer setting after the configuration boundary validated it."""
        value = self.settings.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"setting {name} is not an integer")
        return value

    def string_setting(self, name: str, *, default: str) -> str:
        """Return one text setting after the configuration boundary validated it."""
        value = self.settings.get(name, default)
        if not isinstance(value, str):
            raise TypeError(f"setting {name} is not text")
        return value
