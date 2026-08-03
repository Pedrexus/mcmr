use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};

mod projection;

pub use projection::AttributeProjectionRecord;

/// One short role-type group derived from repository coimports.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CoupledTypeGroupRecord {
    pub prefix: String,
    pub span: SourceSpan,
    #[serde(default)]
    pub role_suffixes: Vec<String>,
    pub type_count: usize,
    pub maximum_type_lines: usize,
    pub coimporting_module_count: usize,
}
