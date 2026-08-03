use crate::protocol::Request;
use std::collections::BTreeMap;
use std::path::PathBuf;

pub(super) struct AnalysisRequest {
    pub(super) root: PathBuf,
    pub(super) typed_families: Vec<String>,
    pub(super) python_standard_library: Vec<String>,
    pub(super) suffixes: Option<Vec<String>>,
    pub(super) generic_schemas: BTreeMap<String, String>,
}

impl AnalysisRequest {
    pub(super) fn kernel_request(&mut self) -> Request {
        let mut request = Request::analysis(self.root.to_string_lossy().into_owned(), Vec::new());
        request.python_standard_library = std::mem::take(&mut self.python_standard_library);
        if let Some(stated) = self.suffixes.take() {
            request.suffixes = stated;
        }
        request
    }
}
