use std::collections::BTreeMap;

use crate::discovery::Document;
use crate::protocol::JsonObject;
use serde_json::{Value, json};
use toml::Table;

use super::fact_identity::FactIdentity;

mod commands;

use commands::{commands_of, runs_unattended, stays_inside};

/// Every lifecycle capability the tooling manifest automates, with what each command commits to.
pub(super) fn automation(tooling: &Table, guides: &[Document]) -> Value {
    let tasks: Vec<Value> = stated_commands(tooling)
        .into_iter()
        .map(|(capability, commands)| task_value(capability, commands, guides))
        .collect();
    JsonObject::new(
        FactIdentity {
            key: "automation:chefe",
            path: "chefe.toml",
        }
        .base(),
    )
    .merged(json!({"tasks": tasks}))
}

fn stated_commands(tooling: &Table) -> BTreeMap<String, Vec<String>> {
    let mut stated: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for table in task_tables(tooling) {
        for (capability, declared) in table {
            let held = stated.entry(capability.clone()).or_default();
            extend_unique(held, commands_of(declared));
        }
    }
    stated
}

fn extend_unique(held: &mut Vec<String>, commands: Vec<String>) {
    for command in commands {
        if !held.contains(&command) {
            held.push(command);
        }
    }
}

fn task_value(capability: String, commands: Vec<String>, guides: &[Document]) -> Value {
    let guidance_locations = guidance_locations(&capability, guides);
    json!({
        "capability": capability,
        "is_repository_owned": commands.iter().all(|command| stays_inside(command)),
        "is_noninteractive": commands.iter().all(|command| runs_unattended(command)),
        "guidance_locations": guidance_locations,
        "commands": commands,
    })
}

fn guidance_locations(capability: &str, guides: &[Document]) -> Vec<String> {
    let invocation = format!("chefe run {capability}");
    guides
        .iter()
        .filter(|guide| {
            guide.source.contains(&invocation)
                || (capability == "setup" && guide.source.contains("chefe install"))
        })
        .map(|guide| guide.relative.clone())
        .collect()
}

/// Return every table of the manifest that declares tasks, which is one per environment plus one.
fn task_tables(tooling: &Table) -> Vec<&Table> {
    let default = tooling.get("tasks").and_then(toml::Value::as_table);
    let scoped = tooling
        .get("envs")
        .and_then(toml::Value::as_table)
        .into_iter()
        .flat_map(|environments| environments.values())
        .filter_map(|environment| environment.get("tasks").and_then(toml::Value::as_table));
    default.into_iter().chain(scoped).collect()
}
