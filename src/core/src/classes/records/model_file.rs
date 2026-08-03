use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};

/// One implementation file below a shared models directory.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ModelFileRecord {
    pub path: String,
    pub span: SourceSpan,
    pub top_level_class_count: usize,
    pub model_class_count: usize,
    #[serde(default)]
    pub is_package_initializer: bool,
}
