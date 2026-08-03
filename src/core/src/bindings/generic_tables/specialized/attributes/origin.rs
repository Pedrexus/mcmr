use super::row::AttributeRow;

#[derive(Clone)]
pub(super) struct AttributeValueOrigin {
    pub(super) parent_id: String,
    pub(super) container_id: String,
    pub(super) container_length: u64,
}

impl AttributeValueOrigin {
    pub(super) fn new(row: &AttributeRow<'_>) -> Self {
        let parent_id = row.record_id.clone();
        Self {
            container_id: format!("{parent_id}/accesses.receiver_type_bases"),
            container_length: row.access.receiver.type_bases.len() as u64,
            parent_id,
        }
    }
}
