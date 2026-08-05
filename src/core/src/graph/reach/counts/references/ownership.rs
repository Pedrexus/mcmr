use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ReferenceOwnership {
    pub owner_references: usize,
    pub non_owner_references: usize,
    pub unresolved_name_references: usize,
}
