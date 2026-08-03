from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from mcmr import (
    Boolean,
    Category,
    MCMRConfiguration,
    Numeric,
    RuleConfiguration,
    is_match,
    validated_setting,
)

from ...support import built_catalog

if TYPE_CHECKING:
    from pathlib import Path


def written_configuration(root: Path, document: str) -> MCMRConfiguration:
    """Write one project document and read its MCMR configuration."""
    (root / "pyproject.toml").write_text(document)
    return MCMRConfiguration.read(root)


def test_project_policy_overrides_change_only_the_selected_rule() -> None:
    """One exact project override changes only its selected rule."""
    configuration = MCMRConfiguration(
        rules={
            "ALL-FUNC0002": RuleConfiguration(policy=Boolean(expected=True)),
            "ALL-ARCH1001": RuleConfiguration(policy=Category(good={"cohesive"})),
        },
    )
    policies = configuration.policies()

    assert policies.overrides["ALL-FUNC0002"] == Boolean(expected=True)


def test_project_policy_overrides_must_cover_the_selected_rule_contract() -> None:
    catalog = built_catalog()
    wrong_shape = MCMRConfiguration(
        rules={"ALL-FUNC0002": RuleConfiguration(policy=Numeric(maximum=1))}
    )
    incomplete = MCMRConfiguration(
        rules={"ALL-ARCH1001": RuleConfiguration(policy=Category(good={"cohesive"}))}
    )

    with pytest.raises(TypeError, match="does not match its bool output"):
        wrong_shape.selected(catalog.definitions, rules=catalog.rules)
    with pytest.raises(ValueError, match="classify every output category"):
        incomplete.selected(catalog.definitions, rules=catalog.rules)


def test_selection_supports_ids_prefixes_shell_patterns_callables_and_exclusions() -> None:
    """A project can state broad ownership and make exact exceptions without silent misses."""
    catalog = built_catalog()
    definition = next(item for item in catalog.definitions if item.id == "ALL-FUNC0002")

    expected_patterns = {
        "ALL-FUNC0002",
        "ALL-FUNC",
        "ALL-FUNC*",
        "functions/ownership/r0002",
    }
    assert expected_patterns == {
        pattern
        for pattern in (*expected_patterns, "PY-*")
        if is_match(rule_id=definition.id, callable_path=definition.callable, pattern=pattern)
    }

    selected = MCMRConfiguration(
        select=("ALL-FUNC*",),
        ignore=("ALL-FUNC0001",),
        rules={"ALL-FUNC0003": RuleConfiguration(enabled=False)},
    ).selected(catalog.definitions, rules=catalog.rules)
    identifiers = {
        item.id
        for item in catalog.definitions
        if item.callable in {rule.callable_path for rule in selected}
    }

    assert (identifiers & {"ALL-FUNC0001", "ALL-FUNC0002", "ALL-FUNC0003"}) | {
        identifier for identifier in identifiers if not identifier.startswith("ALL-FUNC")
    } == {"ALL-FUNC0002"}


def test_selection_rejects_unknown_or_unmatched_rule_patterns() -> None:
    """Unknown exact rules and patterns that select nothing fail loudly."""
    catalog = built_catalog()
    with pytest.raises(ValueError, match="Unknown configured rule ALL-NOPE9999"):
        unknown = MCMRConfiguration(rules={"ALL-NOPE9999": RuleConfiguration()})
        unknown.selected(catalog.definitions, rules=catalog.rules)
    with pytest.raises(ValueError, match="Unknown configured rule ALL-NOPE9999"):
        unknown.settings(catalog.definitions, rules=catalog.rules)
    with pytest.raises(ValueError, match="No rules match"):
        MCMRConfiguration(select=("NOPE-*",)).selected(catalog.definitions, rules=catalog.rules)


def test_rule_settings_are_checked_and_coerced_before_execution() -> None:
    """The engine receives values validated against the selected rule's own annotations."""
    catalog = built_catalog()
    configuration = MCMRConfiguration(
        rules={
            "ALL-FUNC0002": RuleConfiguration(
                settings={"maximum_lines": 4, "ignore_names": ["adapter"]}
            )
        }
    )
    settings, rule = (
        configuration.settings(catalog.definitions, rules=catalog.rules),
        next(item for item in catalog.rules if item.qualname == "single_use_trivial_helper"),
    )

    assert settings[rule.callable_path] == {"maximum_lines": 4, "ignore_names": ["adapter"]}

    invalid = MCMRConfiguration(rules={"ALL-FUNC0002": RuleConfiguration(settings={"missing": 1})})
    with pytest.raises(ValueError, match="Unknown setting for ALL-FUNC0002 missing"):
        invalid.settings(catalog.definitions, rules=catalog.rules)

    assert validated_setting(set[str], ["one", "two"]) == {"one", "two"}
    with pytest.raises(TypeError, match="unsupported type list"):
        validated_setting(list[int], ["1", "2"])


def test_rule_setting_domains_reject_values_outside_their_contracts() -> None:
    """Each declared setting domain rejects values no rule can interpret."""
    catalog = built_catalog()
    invalid_domains = [
        ("ALL-DUPL0003", {"minimum_token_length": 39}, "greater than or equal to 40"),
        ("ALL-FUNC0002", {"maximum_lines": -1}, "greater than or equal to 0"),
        ("ALL-CI0002", {"percentile": 1.1}, "less than or equal to 1"),
    ]
    for rule_id, invalid_settings, message in invalid_domains:
        invalid = MCMRConfiguration(rules={rule_id: RuleConfiguration(settings=invalid_settings)})
        with pytest.raises(ValidationError, match=message):
            invalid.settings(catalog.definitions, rules=catalog.rules)


def test_rule_exclusions_are_keyed_by_the_validated_runtime_callable() -> None:
    catalog = built_catalog()
    configuration = MCMRConfiguration(
        rules={"ALL-FUNC0002": RuleConfiguration(exclude=("tests/**",))}
    )
    definition = next(item for item in catalog.definitions if item.id == "ALL-FUNC0002")

    assert configuration.exclusions(catalog.definitions) == {definition.callable: ["tests/**"]}
