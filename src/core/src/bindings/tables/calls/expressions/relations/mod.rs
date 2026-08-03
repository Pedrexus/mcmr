#[derive(Clone)]
pub(in crate::bindings::tables::calls::expressions) struct ExpressionEdge {
    pub(in crate::bindings::tables::calls::expressions) parent_id: String,
    pub(in crate::bindings::tables::calls::expressions) parent_kind: String,
    pub(in crate::bindings::tables::calls::expressions) child_id: String,
    pub(in crate::bindings::tables::calls::expressions) relation: String,
    pub(in crate::bindings::tables::calls::expressions) ordinal: u64,
}

impl ExpressionEdge {
    pub(super) fn at(place: &ExpressionPlace, [child_id, root_id]: [&str; 2]) -> Self {
        Self {
            parent_id: place
                .parent_id
                .clone()
                .unwrap_or_else(|| root_id.to_string()),
            parent_kind: if place.parent_id.is_some() {
                "expression".to_string()
            } else {
                "call".to_string()
            },
            child_id: child_id.to_string(),
            relation: place.relation.clone(),
            ordinal: place.ordinal as u64,
        }
    }
}

pub(super) mod ancestry;
pub(super) mod mapping;
use super::place::ExpressionPlace;
