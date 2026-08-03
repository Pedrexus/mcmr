use crate::discovery::Document;
use crate::protocol::JsonObject;
use serde_json::{Value, json};
use toml::Table;

use super::command_line::CommandLine;
use super::fact_identity::FactIdentity;

mod assignments;

use assignments::configuration_assignments;

pub(super) fn test_suite(manifest: &Table) -> Value {
    let pytest = manifest
        .get("tool")
        .and_then(|tool| tool.get("pytest"))
        .and_then(|pytest| pytest.get("ini_options"))
        .and_then(toml::Value::as_table);
    let options = pytest
        .map(|table| text_of(table, "addopts"))
        .unwrap_or_default();
    let command = CommandLine::new(&options);
    let coverage = command.has_flag("--cov");
    let strict = command.has_flag("--strict")
        || pytest
            .and_then(|table| table.get("strict"))
            .and_then(toml::Value::as_bool)
            .unwrap_or(false);
    let strict_control = |name: &str, switch: &str| {
        pytest
            .and_then(|table| table.get(name))
            .and_then(toml::Value::as_bool)
            .unwrap_or_else(|| strict || (!switch.is_empty() && command.has_flag(switch)))
    };
    JsonObject::new(
        FactIdentity {
            key: "suite:pytest",
            path: "pyproject.toml",
        }
        .base(),
    )
    .merged(json!({
        "strict_controls": {
            "strict_config": strict_control("strict_config", "--strict-config"),
            "strict_markers": strict_control("strict_markers", "--strict-markers"),
            "strict_parametrization_ids": strict_control("strict_parametrization_ids", ""),
            "strict_xfail": strict_control("strict_xfail", ""),
        },
        "import_mode": command.option("--import-mode")
            .or_else(|| pytest.map(|table| text_of(table, "import_mode")))
            .filter(|mode| !mode.is_empty())
            .unwrap_or_else(|| "prepend".to_string()),
        "anyio_mode": pytest.map(|table| text_of(table, "anyio_mode")).unwrap_or_default(),
        "asyncio_mode": pytest
            .map(|table| text_of(table, "asyncio_mode"))
            .unwrap_or_default(),
        "is_coverage_configured": coverage,
        "is_branch_coverage_enabled": branch_coverage(manifest),
    }))
}

fn branch_coverage(manifest: &Table) -> bool {
    manifest
        .get("tool")
        .and_then(|tool| tool.get("coverage"))
        .and_then(|coverage| coverage.get("run"))
        .and_then(|run| run.get("branch"))
        .and_then(toml::Value::as_bool)
        .unwrap_or(false)
}

pub(super) fn configuration(manifest: &Table, documents: &[Document]) -> Value {
    let project = manifest.get("project").and_then(toml::Value::as_table);
    let requires = project
        .map(|table| text_of(table, "requires-python"))
        .unwrap_or_default();
    let tools = versioned_tools(manifest);
    JsonObject::new(
        FactIdentity {
            key: "configuration:pyproject",
            path: "pyproject.toml",
        }
        .base(),
    )
    .merged(json!({
        "assignments": configuration_assignments(documents),
        "python_target": {
            "project_minimum_minor": minor(&requires),
            "configured_tools": tools,
            "tool_target_minors": target_minors(manifest),
            "per_file_target_minors": per_file_target_minors(manifest),
        },
    }))
}

/// Return the minor version one declaration accepts, however that version is written.
pub(super) fn minor(declaration: &str) -> Option<u32> {
    let specifier = declaration
        .split(',')
        .find(|part| part.contains(">="))
        .unwrap_or(declaration);
    let digits: String = specifier
        .chars()
        .filter(|letter| letter.is_ascii_digit() || *letter == '.')
        .collect();
    match digits.split_once('.') {
        Some((_, minor)) => minor.parse().ok(),
        None => digits
            .strip_prefix('3')
            .and_then(|minor| minor.parse().ok()),
    }
}

/// Every configured tool that states a Python target, whichever key it states it under.
fn versioned_tools(manifest: &Table) -> Vec<String> {
    manifest
        .get("tool")
        .and_then(toml::Value::as_table)
        .map(|table| {
            table
                .iter()
                .filter(|(_, settings)| target_key(settings).is_some())
                .map(|(name, _)| name.clone())
                .collect()
        })
        .unwrap_or_default()
}

fn target_key(settings: &toml::Value) -> Option<&str> {
    ["target-version", "python_version", "python-version"]
        .iter()
        .find_map(|key| settings.get(key).and_then(toml::Value::as_str))
}

fn target_minors(manifest: &Table) -> Value {
    let tools = manifest.get("tool").and_then(toml::Value::as_table);
    let mut targets = serde_json::Map::new();
    for (name, table) in tools.into_iter().flatten() {
        if let Some(value) = target_key(table).and_then(minor) {
            targets.insert(name.clone(), json!(value));
        }
    }
    Value::Object(targets)
}

/// Return every Python minor Ruff assigns to an individual source pattern.
fn per_file_target_minors(manifest: &Table) -> Vec<u32> {
    manifest
        .get("tool")
        .and_then(|tool| tool.get("ruff"))
        .and_then(|ruff| ruff.get("per-file-target-version"))
        .and_then(toml::Value::as_table)
        .into_iter()
        .flat_map(Table::values)
        .filter_map(toml::Value::as_str)
        .filter_map(minor)
        .collect()
}

fn text_of(table: &Table, name: &str) -> String {
    table
        .get(name)
        .and_then(toml::Value::as_str)
        .unwrap_or_default()
        .to_string()
}
