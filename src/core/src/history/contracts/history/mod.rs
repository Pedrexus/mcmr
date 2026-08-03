use serde::Serialize;

mod file_history;
mod history_change;

pub use file_history::FileHistory;
pub use history_change::HistoryChange;

/// What the repository's own history says about each file and commit.
#[derive(Clone, Debug, Default, Serialize)]
pub struct History {
    pub unscoped_commit_count: usize,
    pub files: Vec<FileHistory>,
    pub changes: Vec<HistoryChange>,
}
