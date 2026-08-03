use super::*;
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

/// One request asking about Python alone, which is what the fixtures below write.
fn python_scope(root: &Path) -> crate::discovery::Scope {
    crate::discovery::Scope::of(root, &[".py".to_string()])
}

/// One throwaway repository, built commit by commit and removed when the test ends.
struct Repository {
    root: std::path::PathBuf,
}

impl Repository {
    fn new(name: &str) -> Self {
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "mcmr-history-{}-{name}-{unique}",
            std::process::id()
        ));
        crate::test_support::remove_directory(&root);
        std::fs::create_dir_all(&root).expect("the temporary root is writable");
        let repository = Self { root };
        repository.initialize_identity();
        repository
    }

    /// Commit everything staged at a stated day, so a date assertion is reproducible.
    fn commit(&self, message: &str, author: &str, day: &str) {
        self.git(&["add", "-A"]);
        let stamp = format!("{day}T12:00:00+00:00");
        let finished = Command::new("git")
            .arg("-C")
            .arg(&self.root)
            .args(["commit", "--quiet", "-m", message, "--author"])
            .arg(format!("{author} <{author}@example.com>"))
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("GIT_CONFIG_SYSTEM", "/dev/null")
            .env("GIT_AUTHOR_DATE", &stamp)
            .env("GIT_COMMITTER_DATE", &stamp)
            .output()
            .expect("git answers");
        assert!(finished.status.success(), "the commit failed");
    }

    fn git(&self, arguments: &[&str]) {
        let finished = Command::new("git")
            .arg("-C")
            .arg(&self.root)
            .args(arguments)
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("GIT_CONFIG_SYSTEM", "/dev/null")
            .output()
            .expect("git answers");
        assert!(finished.status.success(), "git {arguments:?} failed");
    }

    fn initialize_identity(&self) {
        self.git(&["init", "--quiet"]);
        self.git(&["config", "user.email", "history@example.com"]);
        self.git(&["config", "user.name", "First Author"]);
        self.git(&["config", "commit.gpgsign", "false"]);
    }

    fn remove(&self, path: &str) {
        std::fs::remove_file(self.root.join(path)).expect("the file is removable");
    }

    fn write(&self, path: &str, text: &str) {
        let full = self.root.join(path);
        std::fs::write(full, text).expect("the file is writable");
    }
}

impl Drop for Repository {
    fn drop(&mut self) {
        crate::test_support::remove_directory(&self.root);
    }
}

fn history(repository: &Repository) -> History {
    scan(&repository.root, &python_scope(&repository.root))
        .expect("the history scan succeeds")
        .expect("the throwaway repository has history")
}

fn file<'a>(history: &'a History, path: &str) -> &'a FileHistory {
    history
        .files
        .iter()
        .find(|entry| entry.path == path)
        .expect("the file is in the history")
}

fn commits(history: &History) -> usize {
    history.changes.len() + history.unscoped_commit_count
}

fn file_commits(history: &FileHistory) -> usize {
    history.author_count + history.additional_commit_count
}

fn scoped_repository() -> Repository {
    let repository = Repository::new("scoped");
    repository.write("engine.py", "value = 1\n");
    repository.write("kernel.cu", "__global__ void scale() {}\n");
    repository.commit("first", "First Author", "2026-09-01");
    repository.write("engine.py", "value = 2\n");
    repository.write("kernel.cu", "__global__ void scale(int n) {}\n");
    repository.commit("second", "First Author", "2026-09-02");
    repository
}

#[test]
fn a_directory_outside_a_repository_reports_nothing_rather_than_failing() {
    let outside = std::env::temp_dir().join(format!("mcmr-history-bare-{}", std::process::id()));
    std::fs::create_dir_all(&outside).expect("the temporary root is writable");

    assert!(
        read(&outside, &python_scope(&outside))
            .expect("absence is not an operational failure")
            .is_empty()
    );
    assert!(
        scan(&outside, &python_scope(&outside))
            .expect("absence is not an operational failure")
            .is_none()
    );

    crate::test_support::remove_directory(&outside);
}

#[test]
fn a_repository_without_commits_reports_no_history() {
    let repository = Repository::new("empty");

    assert!(
        scan(&repository.root, &python_scope(&repository.root))
            .expect("an empty repository is readable")
            .is_none()
    );
}

#[test]
fn an_invalid_surviving_file_cannot_masquerade_as_a_deleted_file() {
    let repository = Repository::new("invalid-utf8");
    repository.write("engine.py", "value = 1\n");
    repository.commit("first", "First Author", "2026-01-01");
    std::fs::write(repository.root.join("engine.py"), [0xff])
        .expect("the invalid fixture is writable");

    let failure = scan(&repository.root, &python_scope(&repository.root))
        .expect_err("an unreadable surviving file must fail history");

    assert!(failure.contains("history file engine.py could not be read as UTF-8"));
}

#[test]
fn each_file_carries_its_commits_its_authors_and_how_long_ago_it_stopped() {
    let repository = Repository::new("counts");
    repository.write("engine.py", "import parser\n");
    repository.write("parser.py", "value = 1\n");
    repository.commit("first", "First Author", "2026-01-01");
    repository.write("engine.py", "import parser\nvalue = 2\n");
    repository.commit("second", "Second Author", "2026-01-11");
    repository.write("engine.py", "import parser\nvalue = 3\n");
    repository.commit("third", "First Author", "2026-01-21");

    let read = history(&repository);

    assert_eq!(
        (
            commits(&read),
            file_commits(file(&read, "engine.py")),
            file(&read, "engine.py").author_count,
            file(&read, "engine.py").days_since_last_change,
            file(&read, "engine.py").line_count,
            file_commits(file(&read, "parser.py")),
            file(&read, "parser.py").author_count,
            file(&read, "parser.py").days_since_last_change,
        ),
        (3, 3, 2, 0, 2, 1, 1, 20)
    );
}

#[test]
fn a_day_count_is_read_against_the_newest_commit_rather_than_against_today() {
    let repository = Repository::new("clock");
    repository.write("stable.py", "value = 1\n");
    repository.commit("first", "First Author", "2019-03-01");
    repository.write("moving.py", "value = 2\n");
    repository.commit("second", "First Author", "2019-03-31");

    // Both commits are years old, so a count against the wall clock would grow on every run
    // and these two files would never sit exactly thirty days apart.
    let read = history(&repository);

    assert_eq!(file(&read, "stable.py").days_since_last_change, 30);
    assert_eq!(file(&read, "moving.py").days_since_last_change, 0);
}

#[test]
fn every_commit_carries_its_requested_paths_once() {
    let repository = Repository::new("pairs");
    for day in 1..=3 {
        repository.write("reader.py", &format!("value = {day}\n"));
        repository.write("writer.py", &format!("value = {day}\n"));
        repository.write("alone.py", &format!("value = {day}\n"));
        repository.commit("edit", "First Author", &format!("2026-02-0{day}"));
        repository.write("alone.py", &format!("extra = {day}\n"));
        repository.commit("alone", "First Author", &format!("2026-02-1{day}"));
    }

    let read = history(&repository);
    let coupled: Vec<&HistoryChange> = read
        .changes
        .iter()
        .filter(|change| {
            change.paths.contains(&"reader.py".to_string())
                && change.paths.contains(&"writer.py".to_string())
        })
        .collect();

    assert_eq!(coupled.len(), 3);
    assert!(coupled.iter().all(|change| change.other_file_count == 0));
    assert_eq!(file_commits(file(&read, "alone.py")), 6);
}

#[test]
fn a_file_carries_the_import_lines_that_explain_co_change() {
    let repository = Repository::new("imports");
    for day in 1..=3 {
        repository.write(
            "reader.py",
            &format!("from . import writer\nvalue = {day}\n"),
        );
        repository.write("writer.py", &format!("value = {day}\n"));
        repository.commit("edit", "First Author", &format!("2026-03-0{day}"));
    }

    let read = history(&repository);

    assert_eq!(file(&read, "reader.py").imports, ["from . import writer"]);
}

#[test]
fn a_wide_commit_states_its_width_without_deciding_whether_it_is_a_sweep() {
    let repository = Repository::new("sweep");
    for index in 0..4 {
        repository.write(&format!("module{index}.py"), "value = 1\n");
    }
    repository.commit("first", "First Author", "2026-04-01");
    for index in 0..4 {
        repository.write(&format!("module{index}.py"), "value = 2\n");
    }
    repository.commit("sweep", "First Author", "2026-04-02");

    let read = history(&repository);

    assert_eq!(file_commits(file(&read, "module0.py")), 2);
    assert_eq!(read.changes.len(), 2);
    assert!(
        read.changes
            .iter()
            .all(|change| change.paths.len() + change.other_file_count == 4)
    );
}

#[test]
fn a_renamed_file_keeps_the_history_it_earned_under_its_old_name() {
    let repository = Repository::new("rename");
    repository.write("old.py", "value = 1\n");
    repository.commit("first", "First Author", "2026-05-01");
    repository.write("old.py", "value = 2\n");
    repository.commit("second", "First Author", "2026-05-02");
    repository.git(&["mv", "old.py", "new.py"]);
    repository.commit("rename", "First Author", "2026-05-03");

    let read = history(&repository);

    assert_eq!(file_commits(file(&read, "new.py")), 3);
    assert!(read.files.iter().all(|entry| entry.path != "old.py"));
}

#[test]
fn a_deleted_file_keeps_its_churn_and_reads_as_no_lines_at_all() {
    let repository = Repository::new("deleted");
    repository.write("gone.py", "value = 1\n");
    repository.commit("first", "First Author", "2026-06-01");
    repository.remove("gone.py");
    repository.commit("second", "First Author", "2026-06-02");

    let read = history(&repository);

    assert_eq!(file_commits(file(&read, "gone.py")), 2);
    assert_eq!(file(&read, "gone.py").line_count, 0);
}

#[test]
fn the_complete_history_has_no_private_commit_ceiling() {
    let repository = Repository::new("ceiling");
    for day in 1..=4 {
        repository.write("engine.py", &format!("value = {day}\n"));
        repository.commit("edit", "First Author", &format!("2026-07-0{day}"));
    }

    let complete = history(&repository);

    assert_eq!(commits(&complete), 4);
    assert_eq!(file_commits(file(&complete, "engine.py")), 4);
}

#[test]
fn commits_stay_linear_instead_of_expanding_into_a_bounded_pair_table() {
    let repository = Repository::new("linear-changes");
    for day in 1..=3 {
        for index in 0..3 {
            repository.write(&format!("module{index}.py"), &format!("value = {day}\n"));
        }
        repository.commit("edit", "First Author", &format!("2026-08-0{day}"));
    }

    let read = history(&repository);

    assert_eq!(read.changes.len(), 3);
    assert!(read.changes.iter().all(|change| change.paths.len() == 3));
}

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

    // Ranking a Python module by churn in a run asked only about CUDA names a file that run
    // never opened. The full commit width remains two even though this request retains one.
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
            read(&repository.root, &python_scope(&repository.root)).expect("history is readable")
                [0]["files"]
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
