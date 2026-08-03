use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::source::is_test_path;
#[cfg(test)]
use files::is_import;
use files::{Tally, contents};
use git::log;

mod contracts;
mod files;
mod git;

pub use contracts::{FileHistory, History, HistoryChange};

/// Read what the repository's own history says about each file and commit.
///
/// Complexity alone names a file that is hard to read. Complexity beside churn names one that is
/// hard to read and keeps being read, which is a different and more urgent thing. Two files that
/// keep changing in the same commit are coupled whatever their imports say, and that coupling is
/// invisible to every other family here.
pub fn read(root: &Path, scope: &crate::discovery::Scope) -> Result<Vec<Value>, String> {
    Ok(scan(root, scope)?.as_ref().map(facts).unwrap_or_default())
}

/// Mine the complete `git log`, or nothing where there is no history to mine.
pub fn scan(root: &Path, scope: &crate::discovery::Scope) -> Result<Option<History>, String> {
    let Some(commits) = log(root)? else {
        return Ok(None);
    };
    let newest = commits
        .iter()
        .map(|commit| commit.seconds)
        .max()
        .expect("a history exists only when at least one commit exists");
    let mut tallies: BTreeMap<String, Tally> = BTreeMap::new();
    let mut changes = Vec::new();
    for commit in &commits {
        let touched: BTreeSet<&str> = commit.paths.iter().map(String::as_str).collect();
        let paths: Vec<&str> = touched
            .iter()
            .copied()
            .filter(|path| scope.holds(path))
            .collect();
        for path in &paths {
            let tally = tallies.entry((*path).to_string()).or_default();
            tally.commit_count += 1;
            tally.last_seconds = tally.last_seconds.max(commit.seconds);
            tally.authors.insert(commit.author.clone());
        }
        if !paths.is_empty() {
            changes.push(HistoryChange {
                other_file_count: touched.len() - paths.len(),
                paths: paths.into_iter().map(str::to_string).collect(),
            });
        }
    }
    let contents = contents(root, &tallies)?;
    Ok(Some(History {
        unscoped_commit_count: commits.len() - changes.len(),
        files: tallies
            .iter()
            .map(|(path, tally)| FileHistory {
                path: path.clone(),
                author_count: tally.authors.len(),
                additional_commit_count: tally.commit_count - tally.authors.len(),
                days_since_last_change: (newest - tally.last_seconds) / 86_400,
                line_count: contents.get(path).map_or(0, |content| content.line_count),
                is_test: is_test_path(path),
                imports: contents
                    .get(path)
                    .map(|content| content.imports.clone())
                    .unwrap_or_default(),
            })
            .collect(),
        changes,
    }))
}

/// Return the one fact carrying both collections, since neither is read without the other.
fn facts(history: &History) -> Vec<Value> {
    vec![json!({
        "key": "history",
        "span": {"path": ""},
        "unscoped_commit_count": history.unscoped_commit_count,
        "files": history.files,
        "changes": history.changes,
    })]
}

#[cfg(test)]
mod tests;
