use serde::Serialize;

mod nodes;

pub use nodes::FunctionNodes;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionPresentation {
    pub visibility: String,
    pub cache_decorator: String,
    pub docstring: String,
    pub sole_reference_owner_class: String,
    #[serde(flatten)]
    pub nodes: FunctionNodes,
}
