use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct UseCounts {
    pub call_count: usize,
    pub instantiate_count: usize,
    pub inherit_count: usize,
    pub import_count: usize,
}
