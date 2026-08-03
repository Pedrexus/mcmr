use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::Command;

/// One commit as the log states it, reduced to what the history collections need.
pub(super) struct Commit {
    pub(super) author: String,
    pub(super) seconds: i64,
    pub(super) paths: Vec<String>,
}

/// The byte that opens a commit header, which no path and no status line can hold.
const MARKER: char = '\u{1}';

/// Ask `git` for the complete history with the paths each commit touched.
pub(super) fn log(root: &Path) -> Result<Option<Vec<Commit>>, String> {
    let repository = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["rev-parse", "--is-inside-work-tree"])
        .output()
        .map_err(|failure| format!("Git could not inspect {}: {failure}", root.display()))?;
    if !repository.status.success() {
        return Ok(None);
    }
    let count = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["rev-list", "--all", "--count"])
        .output()
        .map_err(|failure| {
            format!(
                "Git could not count history in {}: {failure}",
                root.display()
            )
        })?;
    if !count.status.success() {
        return Err(command_failure("count history", root, &count.stderr));
    }
    let count = std::str::from_utf8(&count.stdout)
        .map_err(|failure| format!("Git returned a non-UTF-8 commit count: {failure}"))?
        .trim()
        .parse::<usize>()
        .map_err(|failure| format!("Git returned an invalid commit count: {failure}"))?;
    if count == 0 {
        return Ok(None);
    }
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args([
            "log",
            "-M",
            "--relative",
            "--name-status",
            "--no-merges",
            "--format=\u{1}%H\t%an\t%ct",
        ])
        .output()
        .map_err(|failure| {
            format!(
                "Git could not read history in {}: {failure}",
                root.display()
            )
        })?;
    if !output.status.success() {
        return Err(command_failure("read history", root, &output.stderr));
    }
    let text = std::str::from_utf8(&output.stdout)
        .map_err(|failure| format!("Git returned a non-UTF-8 history: {failure}"))?;
    Ok(Some(parse(text)))
}

fn command_failure(operation: &str, root: &Path, stderr: &[u8]) -> String {
    let detail = String::from_utf8_lossy(stderr);
    format!(
        "Git could not {operation} in {}: {}",
        root.display(),
        detail.trim()
    )
}

/// Turn the log into commits whose paths are the names those files answer to today.
fn parse(text: &str) -> Vec<Commit> {
    let mut commits: Vec<Commit> = Vec::new();
    let mut renames: BTreeMap<String, String> = BTreeMap::new();
    for line in text.split('\n') {
        if let Some(header) = line.strip_prefix(MARKER) {
            commits.push(commit_from(header));
            continue;
        }
        let Some(commit) = commits.last_mut() else {
            continue;
        };
        record_path(line, commit, &mut renames);
    }
    for commit in &mut commits {
        commit.paths = commit
            .paths
            .iter()
            .map(|path| fold(&renames, path))
            .collect();
    }
    commits
}

fn commit_from(header: &str) -> Commit {
    let mut fields = header.split('\t').skip(1);
    Commit {
        author: fields
            .next()
            .expect("a git log header must state its author")
            .to_string(),
        seconds: fields
            .next()
            .expect("a git log header must state its timestamp")
            .parse()
            .expect("a git log timestamp must be an integer"),
        paths: Vec::new(),
    }
}

fn record_path(line: &str, commit: &mut Commit, renames: &mut BTreeMap<String, String>) {
    let fields: Vec<&str> = line.split('\t').collect();
    if fields.len() == 3 && fields[0].starts_with(['R', 'C']) {
        commit.paths.push(fields[2].to_string());
        if fields[0].starts_with('R') {
            renames.insert(fields[1].to_string(), fields[2].to_string());
        }
    } else if fields.len() >= 2 && !fields[1].is_empty() {
        commit.paths.push(fields[1].to_string());
    }
}

/// Follow one path through the rename chain to the name it answers to today.
fn fold(renames: &BTreeMap<String, String>, path: &str) -> String {
    let mut current = path.to_string();
    let mut seen = BTreeSet::from([current.clone()]);
    while let Some(next) = renames.get(&current) {
        current = next.clone();
        if !seen.insert(current.clone()) {
            break;
        }
    }
    current
}
