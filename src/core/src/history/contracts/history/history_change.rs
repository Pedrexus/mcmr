use serde::Serialize;

/// The files from this request that one commit changed, beside the commit's full width.
#[derive(Clone, Debug, Serialize)]
pub struct HistoryChange {
    pub other_file_count: usize,
    pub paths: Vec<String>,
}
