use serde::Serialize;

/// How often one file changed, how many hands changed it, and how long ago that stopped.
#[derive(Clone, Debug, Serialize)]
pub struct FileHistory {
    pub path: String,
    pub author_count: usize,
    pub additional_commit_count: usize,
    pub days_since_last_change: i64,
    pub line_count: usize,
    pub is_test: bool,
    pub imports: Vec<String>,
}
