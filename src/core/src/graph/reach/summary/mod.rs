use super::declaration::Declaration;
use crate::graph::contracts::Language;
use serde::Serialize;

/// Where one module's declarations are used across the repository.
#[derive(Debug, Serialize)]
pub struct Reach {
    pub module: String,
    pub path: String,
    pub language: Language,
    pub is_test_module: bool,
    pub declarations: Vec<Declaration>,
}
