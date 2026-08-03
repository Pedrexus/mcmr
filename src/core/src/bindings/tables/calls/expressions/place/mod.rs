#[derive(Clone)]
pub(in crate::bindings::tables::calls::expressions) struct ExpressionPlace {
    pub(super) parent_id: Option<String>,
    pub(super) relation: String,
    pub(super) ordinal: usize,
    pub(super) root_relation: String,
    pub(super) root_ordinal: usize,
    pub(super) depth: usize,
}

impl ExpressionPlace {
    pub(super) fn root(relation: &str, ordinal: usize) -> Self {
        Self {
            parent_id: None,
            relation: relation.to_string(),
            ordinal,
            root_relation: relation.to_string(),
            root_ordinal: ordinal,
            depth: 0,
        }
    }

    pub(super) fn child(&self, parent_id: String, relation: &str, ordinal: usize) -> Self {
        Self {
            parent_id: Some(parent_id),
            relation: relation.to_string(),
            ordinal,
            root_relation: self.root_relation.clone(),
            root_ordinal: self.root_ordinal,
            depth: self.depth + 1,
        }
    }
}
