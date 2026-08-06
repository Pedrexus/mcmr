use super::Expression;
use crate::protocol::Node;
use serde::{Deserialize, Serialize};

/// One resolved invocation and the source properties shared by call rules.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CallSite {
    pub qualified_name: String,
    pub path: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub arguments: Vec<Expression>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub keyword_names: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub receiver: Option<Expression>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub assigned_target: String,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub result_is_discarded: bool,
    pub node: Node,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub callee: Option<Node>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub target_id: String,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_external: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_standard_library: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_first_party: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_constructor: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_shadowed: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub has_ambiguous_alias: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_decorator_factory: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub has_starred_arguments: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub enclosing_is_async: bool,
}

impl CallSite {
    /// Start one call with its provider-guaranteed name and addressed syntax node.
    pub fn new(qualified_name: String, node: Node) -> Self {
        let path = node.span.path.clone();
        Self {
            qualified_name,
            path,
            arguments: Vec::new(),
            keyword_names: Vec::new(),
            receiver: None,
            assigned_target: String::new(),
            result_is_discarded: false,
            node,
            callee: None,
            target_id: String::new(),
            is_external: false,
            is_standard_library: false,
            is_first_party: false,
            is_constructor: false,
            is_shadowed: false,
            has_ambiguous_alias: false,
            is_decorator_factory: false,
            has_starred_arguments: false,
            enclosing_is_async: false,
        }
    }

    pub(super) fn span_key(&self) -> (usize, usize, usize, usize) {
        (
            self.node.span.start_line,
            self.node.span.start_column,
            self.node.span.end_line,
            self.node.span.end_column,
        )
    }
}
