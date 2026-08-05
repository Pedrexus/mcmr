use super::*;

#[test]
fn the_history_answers_for_the_files_the_same_request_would_have_read() {
    let repository = scoped_repository();

    let native = crate::discovery::Scope::of(&repository.root, &[".cu".to_string()]);
    let emitted = read(&repository.root, &native).expect("history is readable");
    let named: Vec<&str> = emitted[0]["files"]
        .as_array()
        .expect("a file list")
        .iter()
        .map(|file| file["path"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(
        (named, &emitted[0]["unscoped_commit_count"]),
        (vec!["kernel.cu"], &serde_json::json!(0))
    );
    assert!(
        emitted[0]["changes"]
            .as_array()
            .expect("a change list")
            .iter()
            .all(|change| change["other_file_count"] == 1
                && change["paths"]
                    .as_array()
                    .is_some_and(|paths| paths.len() == 1))
    );
    assert_eq!(
        read(&repository.root, &python_scope(&repository.root)).expect("history is readable")[0]
            ["files"]
            .as_array()
            .expect("a file list")
            .len(),
        1
    );
}

#[test]
fn one_fact_carries_files_and_commits_from_the_same_log_read() {
    let repository = Repository::new("fact");
    repository.write("engine.py", "value = 1\n");
    repository.commit("first", "First Author", "2026-09-01");

    let emitted =
        read(&repository.root, &python_scope(&repository.root)).expect("history is readable");

    assert_eq!(emitted.len(), 1);
    assert_eq!(emitted[0]["key"], "history");
    assert!(emitted[0]["files"].is_array());
    assert!(emitted[0]["changes"].is_array());
}

#[test]
fn dependency_lines_are_retained_without_a_language_specific_path_allowlist() {
    assert!(is_import("#include <vector>"));
    assert!(is_import("const parser = require('./parser')"));
    assert!(!is_import("value = 1"));
}

#[test]
fn a_test_says_so_however_its_language_spells_the_convention() {
    assert!(is_test_path("tests/test_engine.py"));
    assert!(is_test_path("src/conftest.py"));
    assert!(is_test_path("src/engine_test.rs"));
    assert!(is_test_path("web/engine.spec.ts"));
    assert!(is_test_path("src/__tests__/engine.ts"));
    assert!(!is_test_path("src/engine.py"));
    assert!(!is_test_path("src/latest.py"));
}
