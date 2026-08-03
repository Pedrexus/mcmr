use crate::protocol::Node;
use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionNodes {
    pub sole_reference_owner_definition: Option<Node>,
    pub definition: Option<Node>,
    pub body_expression: Option<Node>,
    pub references: Vec<Node>,
}
