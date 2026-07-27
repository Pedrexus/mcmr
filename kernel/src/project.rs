use serde_json::{Value, json};
use std::path::Path;
use toml::Table;

/// The facts a repository states about itself in its own configuration files.
///
/// A project declares its test runner, its supported language version, and the commands that
/// operate it in configuration rather than in source. Reading that configuration keeps those rules
/// on the same evidence contract as every other rule instead of asking a project to restate what
/// it already wrote down.
///
/// A file the repository does not hold states nothing, so no family is built from one. Reading a
/// missing manifest as an empty one produced a configuration fact at `pyproject.toml:1:1`
/// and a task fact at `chefe.toml:1:1` for a repository holding neither, and the rules reading them
/// then failed against files nobody could open. A project that declares nothing and a project that
/// declares nothing worth reporting are different states, and only the second one has evidence.
pub fn facts(root: &Path, families: &[String]) -> Vec<(String, Value)> {
    let manifest = read_table(&root.join("pyproject.toml"));
    let tooling = read_table(&root.join("chefe.toml"));
    let mut built = Vec::new();
    let wants = |name: &str| families.iter().any(|family| family == name);
    if let Some(stated) = &manifest {
        if wants("TestSuiteFact") {
            built.push(("TestSuiteFact".to_string(), test_suite(stated)));
        }
        if wants("ProjectConfigurationFact") {
            built.push((
                "ProjectConfigurationFact".to_string(),
                configuration(stated),
            ));
        }
    }
    if let Some(stated) = &tooling
        && wants("AutomationTaskFact")
    {
        built.push(("AutomationTaskFact".to_string(), automation(stated)));
    }
    built
}

fn read_table(path: &Path) -> Option<Table> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| text.parse::<Table>().ok())
}

fn base(key: &str, path: &str) -> Value {
    json!({"key": key, "span": {"path": path}, "language": "python"})
}

fn merge(mut left: Value, right: Value) -> Value {
    if let (Some(target), Some(extra)) = (left.as_object_mut(), right.as_object()) {
        for (name, value) in extra {
            target.insert(name.clone(), value.clone());
        }
    }
    left
}

fn test_suite(manifest: &Table) -> Value {
    let pytest = manifest
        .get("tool")
        .and_then(|tool| tool.get("pytest"))
        .and_then(|pytest| pytest.get("ini_options"))
        .and_then(toml::Value::as_table);
    let options = pytest
        .map(|table| text_of(table, "addopts"))
        .unwrap_or_default();
    let coverage = options.contains("--cov");
    merge(
        base("suite:pytest", "pyproject.toml"),
        json!({
            "strict_mode": options.contains("--strict-markers"),
            "strict_controls": {
                "markers": options.contains("--strict-markers"),
                "config": options.contains("--strict-config"),
            },
            "import_mode": pytest
                .map(|table| text_of(table, "import_mode"))
                .filter(|mode| !mode.is_empty())
                .unwrap_or_else(|| "prepend".to_string()),
            "anyio_mode": pytest.map(|table| text_of(table, "anyio_mode")).unwrap_or_default(),
            "asyncio_mode": pytest
                .map(|table| text_of(table, "asyncio_mode"))
                .unwrap_or_default(),
            "is_coverage_configured": coverage,
            "is_branch_coverage_enabled": branch_coverage(manifest),
            "quarantined_tests": [],
        }),
    )
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

fn configuration(manifest: &Table) -> Value {
    let project = manifest.get("project").and_then(toml::Value::as_table);
    let requires = project
        .map(|table| text_of(table, "requires-python"))
        .unwrap_or_default();
    let tools = versioned_tools(manifest);
    merge(
        base("configuration:pyproject", "pyproject.toml"),
        json!({
            "assignments": [],
            "python_target": {
                "project_minimum_minor": minor(&requires),
                "configured_tools": tools,
                "tool_target_minors": target_minors(manifest),
                "per_file_target_minors": [],
            },
        }),
    )
}

/// Return the minor version one declaration accepts, however that version is written.
///
/// A project states `>=3.14`, a formatter states `py314`, and a type checker states `3.14`. All
/// three name the same minor, so all three are read here rather than in three callers.
fn minor(declaration: &str) -> Option<u32> {
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
///
/// Only a tool this kernel knows how to read is named, because a rule comparing targets must not
/// treat a formatter with no version key as a tool that forgot to declare one.
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

/// Every lifecycle capability the tooling manifest automates, with what each command commits to.
///
/// A capability can be stated more than once, since the default table and each environment table
/// declare their own, so the commands are grouped by capability rather than listed one task at a
/// time. Two different commands under one name is exactly the state where no command is canonical.
fn automation(tooling: &Table) -> Value {
    let mut stated: std::collections::BTreeMap<String, Vec<String>> =
        std::collections::BTreeMap::new();
    for table in task_tables(tooling) {
        for (capability, declared) in table {
            let held = stated.entry(capability.clone()).or_default();
            for command in commands_of(declared) {
                if !held.contains(&command) {
                    held.push(command);
                }
            }
        }
    }
    let tasks: Vec<Value> = stated
        .into_iter()
        .map(|(capability, commands)| {
            json!({
                "capability": capability,
                "is_repository_owned": commands.iter().all(|command| stays_inside(command)),
                "is_noninteractive": commands.iter().all(|command| runs_unattended(command)),
                "commands": commands,
            })
        })
        .collect();
    merge(
        base("automation:chefe", "chefe.toml"),
        json!({"tasks": tasks}),
    )
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

/// Return the command one declared task runs, however the manifest spells the declaration.
///
/// A bare string is the command. A table states it under `run` in the source manifest and under
/// `cmd` in the one that manifest compiles to, either as one line or as the words of one. A table
/// stating neither is automated by the tasks it names instead, so those stand in as its command,
/// which keeps the capability discoverable rather than reading as one nobody automated.
fn commands_of(declared: &toml::Value) -> Vec<String> {
    let stated = ["run", "cmd"]
        .iter()
        .find_map(|key| declared.get(key))
        .or(Some(declared));
    match stated {
        Some(toml::Value::String(command)) => vec![command.clone()],
        Some(toml::Value::Array(parts)) => vec![joined(parts, " ")],
        _ => depends_on(declared),
    }
}

fn depends_on(declared: &toml::Value) -> Vec<String> {
    ["depends", "depends-on", "depends_on"]
        .iter()
        .find_map(|key| declared.get(key))
        .and_then(toml::Value::as_array)
        .filter(|named| !named.is_empty())
        .map(|named| vec![joined(named, " && ")])
        .unwrap_or_default()
}

fn joined(parts: &[toml::Value], separator: &str) -> String {
    parts
        .iter()
        .filter_map(toml::Value::as_str)
        .collect::<Vec<_>>()
        .join(separator)
}

/// Whether one command operates this checkout through the environment the manifest declares.
///
/// A task states what a repository does to itself, and it stops being the repository's own the
/// moment running it needs more than this checkout and the environment the manifest declares.
/// Three shapes say so in the command itself. It runs somewhere else or as somebody else, it
/// installs into the machine or fetches from the network instead of using that environment, or the
/// program it runs is an absolute path or a path under one person's home directory.
///
/// An absolute path in an argument is deliberately left alone. A build writing to a scratch
/// directory every machine has is still fully carried by the clone, and telling that apart from a
/// dependency on a machine file needs to know which way the data flows, which a command does not
/// say.
fn stays_inside(command: &str) -> bool {
    const ELSEWHERE: &[&str] = &[
        "sudo", "doas", "su", "ssh", "scp", "apt", "apt-get", "brew", "dnf", "yum", "pacman",
        "apk", "choco", "winget", "snap", "curl", "wget",
    ];
    !heads(command)
        .any(|head| ELSEWHERE.contains(&head) || head.starts_with('/') || head.starts_with('~'))
        && !command.contains("$HOME")
        && !command.contains("~/")
}

/// Whether one command completes with nobody at the terminal.
///
/// Automation is only automation where a machine can run it, so a command asking a person for an
/// answer is not automated however faithfully the manifest records it. What asks is in the command
/// itself, either as a flag that opens a session or as a program that is a terminal session.
fn runs_unattended(command: &str) -> bool {
    const ATTENDED: &[&str] = &["vi", "vim", "nano", "emacs", "less", "more", "gdb", "lldb"];
    const SESSION: &[&str] = &["-it", "-ti", "--interactive", "--pdb", "--edit"];
    !heads(command).any(|head| ATTENDED.contains(&head))
        && !words(command).any(|word| SESSION.contains(&word))
}

/// Return the words one shell command states, with the operators that join them dropped.
fn words(command: &str) -> impl Iterator<Item = &str> {
    segments(command).flat_map(str::split_whitespace)
}

/// Return the program each part of one shell command runs.
fn heads(command: &str) -> impl Iterator<Item = &str> {
    segments(command).filter_map(|segment| segment.split_whitespace().next())
}

/// Split one command wherever a shell would start reading a new one.
///
/// A task is often a script rather than a line, and a newline separates two commands exactly as a
/// semicolon does, so a script escalating privilege three lines down has to be as visible as one
/// that does it first.
fn segments(command: &str) -> impl Iterator<Item = &str> {
    command
        .split(['&', '|', ';', '\n'])
        .filter(|part| !part.is_empty())
}

fn text_of(table: &Table, name: &str) -> String {
    table
        .get(name)
        .and_then(toml::Value::as_str)
        .unwrap_or_default()
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_repository_declaring_no_manifest_states_nothing_about_itself() {
        let bare = std::env::temp_dir().join(format!("mcmr-project-bare-{}", std::process::id()));
        std::fs::create_dir_all(&bare).expect("the temporary root is writable");

        let built = facts(
            &bare,
            &[
                "TestSuiteFact".to_string(),
                "ProjectConfigurationFact".to_string(),
                "AutomationTaskFact".to_string(),
            ],
        );

        // Reading a missing manifest as an empty one put a configuration fact at
        // `pyproject.toml:1:1` and a task fact at `chefe.toml:1:1` into every native repository,
        // and two rules then failed against files nobody could open.
        assert!(built.is_empty());
        let _ = std::fs::remove_dir_all(&bare);
    }

    #[test]
    fn a_repository_that_does_declare_one_is_read_the_way_it_always_was() {
        let held = std::env::temp_dir().join(format!("mcmr-project-held-{}", std::process::id()));
        std::fs::create_dir_all(&held).expect("the temporary root is writable");
        std::fs::write(
            held.join("pyproject.toml"),
            "[project]\nrequires-python = \">=3.14\"\n",
        )
        .expect("the temporary root is writable");

        let built = facts(&held, &["ProjectConfigurationFact".to_string()]);

        assert_eq!(built.len(), 1);
        assert_eq!(built[0].1["python_target"]["project_minimum_minor"], 14);
        let _ = std::fs::remove_dir_all(&held);
    }

    #[test]
    fn a_requires_python_specifier_yields_its_minimum_minor() {
        assert_eq!(minor(">=3.14"), Some(14));
        assert_eq!(minor(">=3.11,<4"), Some(11));
        assert_eq!(minor("py314"), Some(14));
        assert_eq!(minor("3.14"), Some(14));
    }

    #[test]
    fn the_test_suite_reads_its_strictness_from_the_manifest() {
        let manifest: Table = r#"
[tool.pytest.ini_options]
addopts = "-q --strict-markers --cov=mcmr"

[tool.coverage.run]
branch = true
"#
        .parse()
        .unwrap();
        let suite = test_suite(&manifest);

        assert_eq!(suite["strict_mode"], true);
        assert_eq!(suite["is_coverage_configured"], true);
        assert_eq!(suite["is_branch_coverage_enabled"], true);
        assert_eq!(suite["import_mode"], "prepend");
    }

    fn task(tooling: &str, capability: &str) -> Value {
        automation(&tooling.parse::<Table>().expect("the manifest parses"))["tasks"]
            .as_array()
            .expect("a task list")
            .iter()
            .find(|task| task["capability"] == capability)
            .expect("the capability is declared")
            .clone()
    }

    #[test]
    fn tasks_become_the_capabilities_a_repository_owns() {
        let stated = task("[tasks]\ntest = \"python -m pytest\"\n", "test");

        assert_eq!(stated["commands"][0], "python -m pytest");
        assert_eq!(stated["is_repository_owned"], true);
        assert_eq!(stated["is_noninteractive"], true);
    }

    #[test]
    fn a_command_leaving_the_checkout_is_not_the_repositorys_own() {
        let manifest = concat!(
            "[tasks]\n",
            "setup = \"sudo apt-get install -y libfoo\"\n",
            "deploy = \"ssh build@host make release\"\n",
            "seed = \"/usr/local/bin/seeder --rows 10\"\n",
            "home = \"cargo build --target-dir $HOME/target\"\n",
            "fetch = \"curl https://example.com/install.sh\"\n",
            "build = \"python -m build --outdir /tmp/dist\"\n",
        );

        for capability in ["setup", "deploy", "seed", "home", "fetch"] {
            assert_eq!(task(manifest, capability)["is_repository_owned"], false);
        }
        assert_eq!(task(manifest, "build")["is_repository_owned"], true);
    }

    #[test]
    fn a_command_wanting_somebody_at_the_terminal_is_not_automated() {
        let manifest = concat!(
            "[tasks]\n",
            "edit = \"vim CHANGELOG.md\"\n",
            "shell = \"docker run -it project bash\"\n",
            "debug = \"python -m pytest --pdb\"\n",
            "test = \"python -m pytest\"\n",
        );

        for capability in ["edit", "shell", "debug"] {
            assert_eq!(task(manifest, capability)["is_noninteractive"], false);
        }
        assert_eq!(task(manifest, "test")["is_noninteractive"], true);
    }

    #[test]
    fn one_capability_two_environments_declare_carries_both_commands() {
        let manifest = concat!(
            "[tasks]\n",
            "test = \"python -m pytest\"\n",
            "[envs.ci.tasks]\n",
            "test = \"python -m pytest -x\"\n",
            "lint = { cmd = [\"ruff\", \"check\", \".\"] }\n",
        );

        assert_eq!(
            task(manifest, "test")["commands"],
            json!(["python -m pytest", "python -m pytest -x"])
        );
        assert_eq!(task(manifest, "lint")["commands"], json!(["ruff check ."]));
    }

    #[test]
    fn a_script_is_read_line_by_line_the_way_a_shell_reads_it() {
        let manifest = concat!(
            "[tasks.setup]\n",
            "run = '''\n",
            "shell_path=\"$(command -v zsh)\"\n",
            "sudo chsh -s \"$shell_path\" \"$USER\"\n",
            "'''\n",
        );

        assert_eq!(task(manifest, "setup")["is_repository_owned"], false);
    }

    #[test]
    fn a_task_stating_only_what_it_depends_on_is_automated_by_those() {
        let manifest = concat!(
            "[tasks]\n",
            "build = { run = \"python -m build\", description = \"wheel and sdist\" }\n",
            "test = { depends = [\"test-kernel\", \"test-python\"] }\n",
        );

        assert_eq!(
            task(manifest, "build")["commands"],
            json!(["python -m build"])
        );
        assert_eq!(
            task(manifest, "test")["commands"],
            json!(["test-kernel && test-python"])
        );
        assert_eq!(task(manifest, "test")["is_repository_owned"], true);
    }
}
