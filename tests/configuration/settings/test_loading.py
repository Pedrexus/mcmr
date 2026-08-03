from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from mcmr import (
    Boolean,
    Category,
    ContextBackend,
    ExecutionConfiguration,
    ExecutionOverride,
    MCMRConfiguration,
    Numeric,
    RuleConfiguration,
    RulePolicies,
    ScanConfiguration,
)

from ...support import built_catalog

if TYPE_CHECKING:
    from pathlib import Path


def written_configuration(root: Path, document: str) -> MCMRConfiguration:
    """Write one project document and read its MCMR configuration."""
    (root / "pyproject.toml").write_text(document)
    return MCMRConfiguration.read(root)


def test_configuration_uses_complete_defaults_without_a_project_table(tmp_path: Path) -> None:
    """A missing file and a file without MCMR policy both select the complete catalog."""
    missing = MCMRConfiguration.read(tmp_path)
    unconfigured = written_configuration(tmp_path, "[project]\nname = 'sample'\n")

    assert (
        missing.select,
        unconfigured.policies(),
        MCMRConfiguration().scan,
    ) == (["*"], RulePolicies(), ScanConfiguration())


def test_configuration_reads_project_scan_and_execution_choices(tmp_path: Path) -> None:
    """Read project selection, scanning, execution, and contextual backend choices."""
    configured = written_configuration(
        tmp_path,
        """[tool.mcmr]
select = ['PY-*']
[tool.mcmr.scan]
suffixes = ['.py']
[tool.mcmr.execution]
deterministic = true
contextual = true
external = false
[tool.mcmr.contextual]
backend = 'codex'
model = 'gpt-test'
""",
    )

    assert (
        configured.select,
        configured.scan.suffixes,
        configured.execution,
        configured.contextual.backend,
        configured.contextual.model,
    ) == (
        ["PY-*"],
        [".py"],
        ExecutionConfiguration(contextual=True),
        ContextBackend.CODEX,
        "gpt-test",
    )


def test_configuration_reads_contextual_process_choices(tmp_path: Path) -> None:
    """Read the contextual process command, model, effort, and timeout together."""
    configured = written_configuration(
        tmp_path,
        """[tool.mcmr.contextual]
binary = 'codex-test'
model = 'gpt-test'
reasoning_effort = 'high'
timeout_seconds = 45
""",
    )

    assert (
        configured.contextual.binary,
        configured.contextual.model,
        configured.contextual.reasoning_effort,
        configured.contextual.timeout_seconds,
    ) == ("codex-test", "gpt-test", "high", 45)


def test_configuration_rejects_invalid_nested_choices() -> None:
    """Reject unknown scan fields and nonpositive execution bounds."""
    invalid = [
        ({"scan": {"exclude": ["generated/**"]}}, "exclude"),
        ({"execution": {"worker_limit": 0}}, "extra_forbidden"),
        ({"contextual": {"timeout_seconds": 0}}, "greater_than"),
    ]
    for document, message in invalid:
        with pytest.raises(ValidationError, match=message):
            MCMRConfiguration.model_validate(document)


def test_execution_modes_filter_lanes_and_external_evidence_independently() -> None:
    catalog = built_catalog()
    deterministic = next(
        item for item in catalog.definitions if item.lane == "deterministic" and not item.external
    )
    contextual = next(item for item in catalog.definitions if item.lane == "contextual")
    local_contextual = contextual.model_copy(
        update={"identity": contextual.identity.model_copy(update={"external": False})}
    )
    external = contextual.model_copy(
        update={"identity": contextual.identity.model_copy(update={"external": True})}
    )

    assert ExecutionConfiguration().includes(
        external=deterministic.external,
        lane=deterministic.lane,
    )
    assert not ExecutionConfiguration().includes(
        external=local_contextual.external,
        lane=local_contextual.lane,
    )
    assert not ExecutionConfiguration(contextual=True).includes(
        external=external.external,
        lane=external.lane,
    )
    assert ExecutionConfiguration(contextual=True, external=True).includes(
        external=external.external,
        lane=external.lane,
    )


def test_execution_overrides_preserve_unspecified_project_choices() -> None:
    """Command choices change only the execution modes the caller explicitly states."""
    configured = MCMRConfiguration(
        execution=ExecutionConfiguration(deterministic=False, contextual=True)
    )
    unchanged = configured.with_execution()
    overridden = configured.with_execution(
        deterministic=ExecutionOverride.ENABLED,
        contextual=ExecutionOverride.DISABLED,
    )

    assert unchanged.execution == configured.execution
    assert overridden.execution == ExecutionConfiguration(deterministic=True)


def test_configuration_does_not_treat_an_unreadable_project_file_as_absent(
    tmp_path: Path,
) -> None:
    """A broken project file must not silently select the default policy."""
    (tmp_path / "pyproject.toml").mkdir()

    with pytest.raises(IsADirectoryError):
        MCMRConfiguration.read(tmp_path)


def test_compact_rule_tables_collect_settings_and_infer_policy_shapes() -> None:
    """TOML stays lean while the runtime receives explicit typed fields."""
    configured = RuleConfiguration.model_validate(
        {
            "maximum_lines": 3,
            "exclude": ["tests/**"],
            "settings": {"ignore_names": ["keep"]},
            "policy": {"maximum": 2},
        }
    )

    assert (configured.settings, configured.exclude, configured.policy) == (
        {"maximum_lines": 3, "ignore_names": ["keep"]},
        ["tests/**"],
        Numeric(maximum=2),
    )
    assert RuleConfiguration.model_validate({"policy": {"expected": True}}).policy == Boolean(
        expected=True
    )
    assert RuleConfiguration.model_validate(
        {"policy": {"good": ["good"], "neutral": ["unknown"], "bad": ["bad"]}}
    ).policy == Category(good={"good"}, neutral={"unknown"}, bad={"bad"})
    assert RuleConfiguration.model_validate(
        {"policy": {"kind": "numeric", "minimum": 1}}
    ).policy == Numeric(minimum=1)
    assert RuleConfiguration.model_validate({"policy": None}).policy is None

    invalid = [
        ({"maximum_lines": 2, "settings": {"maximum_lines": 3}}, "repeat"),
        ({"settings": 3}, None),
        (3, None),
    ]
    for value, match in invalid:
        with pytest.raises(ValidationError, match=match):
            RuleConfiguration.model_validate(value)
