use super::parameter::ParameterDeclaration;
use serde::Serialize;

/// How one class writes down one member, exactly as its own declaration reads.
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Declaration {
    pub(crate) name: String,
    pub(crate) parameters: Option<Vec<ParameterDeclaration>>,
    pub(crate) decorators: Vec<String>,
    pub(crate) asynchronous: bool,
    pub(crate) line: usize,
    pub(crate) source: String,
}
