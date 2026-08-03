use super::*;
use crate::discovery::Document;
use serde_json::json;

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
        &Inventory::default(),
    )
    .expect("an absent manifest is valid");

    // Reading a missing manifest as an empty one put a configuration fact at
    // `pyproject.toml:1:1` and a task fact at `chefe.toml:1:1` into every native repository,
    // and two rules then failed against files nobody could open.
    assert!(built.is_empty());
    crate::test_support::remove_directory(&bare);
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

    let built = facts(
        &held,
        &["ProjectConfigurationFact".to_string()],
        &Inventory::default(),
    )
    .expect("the manifest is valid");

    assert_eq!(built.len(), 1);
    assert_eq!(built[0].1["python_target"]["project_minimum_minor"], 14);
    crate::test_support::remove_directory(&held);
}

#[test]
fn project_configuration_keeps_source_policies_and_per_file_targets() {
    let held =
        std::env::temp_dir().join(format!("mcmr-project-source-policy-{}", std::process::id()));
    std::fs::create_dir_all(&held).expect("the temporary root is writable");
    std::fs::write(
        held.join("pyproject.toml"),
        concat!(
            "[project]\nrequires-python = \">=3.14\"\n\n",
            "[tool.ruff.per-file-target-version]\n",
            "\"scripts/*.py\" = \"py313\"\n",
        ),
    )
    .expect("the temporary root is writable");
    let documents = vec![Document {
        relative: "src/settings.py".to_string(),
        source: concat!(
            "ignored_directories = ('.cache', 'build', 'vendor')\n\n",
            "class ScanConfiguration:\n",
            "    ignored_suffixes = ('.pyc', '.so', '.tmp')\n",
        )
        .to_string(),
    }];

    let built = facts(
        &held,
        &["ProjectConfigurationFact".to_string()],
        &Inventory {
            documents,
            ..Inventory::default()
        },
    )
    .expect("the manifest and source are valid");
    let configuration = &built[0].1;

    assert_eq!(
        json!([
            configuration["python_target"]["per_file_target_minors"],
            configuration["assignments"].as_array().unwrap().len(),
            configuration["assignments"][0]["is_typed_configuration_field"],
            configuration["assignments"][1]["is_typed_configuration_field"],
        ]),
        json!([[13], 2, false, true])
    );
    crate::test_support::remove_directory(&held);
}

#[test]
fn an_invalid_owned_manifest_fails_instead_of_erasing_its_facts() {
    let held = std::env::temp_dir().join(format!("mcmr-project-invalid-{}", std::process::id()));
    std::fs::create_dir_all(&held).expect("the temporary root is writable");
    std::fs::write(held.join("pyproject.toml"), "[project\n")
        .expect("the temporary root is writable");

    let failure = facts(
        &held,
        &["ProjectConfigurationFact".to_string()],
        &Inventory::default(),
    )
    .expect_err("invalid project evidence must fail");

    assert!(failure.contains("pyproject.toml is not valid TOML"));
    crate::test_support::remove_directory(&held);
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

    assert_eq!(suite["strict_controls"]["strict_config"], false);
    assert_eq!(suite["strict_controls"]["strict_markers"], true);
    assert_eq!(
        suite["strict_controls"]["strict_parametrization_ids"],
        false
    );
    assert_eq!(suite["strict_controls"]["strict_xfail"], false);
    assert_eq!(suite["is_coverage_configured"], true);
    assert_eq!(suite["is_branch_coverage_enabled"], true);
    assert_eq!(suite["import_mode"], "prepend");
}

#[test]
fn pytest_global_strictness_and_import_flags_are_effective_configuration() {
    let manifest: Table = r#"
[tool.pytest.ini_options]
addopts = "--strict --import-mode=importlib"
strict_xfail = false
"#
    .parse()
    .unwrap();
    let suite = test_suite(&manifest);

    assert_eq!(suite["strict_controls"]["strict_config"], true);
    assert_eq!(suite["strict_controls"]["strict_markers"], true);
    assert_eq!(suite["strict_controls"]["strict_parametrization_ids"], true);
    assert_eq!(suite["strict_controls"]["strict_xfail"], false);
    assert_eq!(suite["import_mode"], "importlib");
}

fn task(tooling: &str, capability: &str) -> Value {
    automation(&tooling.parse::<Table>().expect("the manifest parses"), &[])["tasks"]
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
fn tasks_retain_the_guides_that_name_their_public_invocation() {
    let guides = [
        Document {
            relative: "README.md".to_string(),
            source: "Run `chefe run test` before opening a change.".to_string(),
        },
        Document {
            relative: "docs/setup.md".to_string(),
            source: "Start with `chefe install`.".to_string(),
        },
    ];
    let tasks = automation(
        &"[tasks]\nsetup = \"maturin develop\"\ntest = \"python -m pytest\"\n"
            .parse::<Table>()
            .expect("the manifest parses"),
        &guides,
    );
    let records = tasks["tasks"].as_array().expect("a task list");
    let locations = |capability: &str| {
        records
            .iter()
            .find(|task| task["capability"] == capability)
            .expect("the capability is declared")["guidance_locations"]
            .clone()
    };

    assert_eq!(locations("setup"), json!(["docs/setup.md"]));
    assert_eq!(locations("test"), json!(["README.md"]));
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

#[test]
fn a_malformed_command_array_never_becomes_a_partial_command() {
    let stated = task(
        "[tasks.test]\ncmd = [\"python\", 3, \"-m pytest\"]\n",
        "test",
    );

    assert_eq!(stated["commands"], json!([]));
}
