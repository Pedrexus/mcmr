use crate::graph::ParameterKind;
use serde::Serialize;

/// One parameter of one declaration, as the language holding it binds an argument to it.
#[derive(Clone, Debug, Serialize)]
pub(crate) struct ParameterDeclaration {
    pub(crate) name: String,
    pub(crate) kind: ParameterKind,
    pub(crate) has_default: bool,
}
