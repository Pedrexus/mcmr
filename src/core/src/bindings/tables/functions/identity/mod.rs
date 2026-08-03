use crate::functions::FunctionRecord;

pub(super) fn entity_id(record: &FunctionRecord) -> &str {
    record
        .presentation
        .nodes
        .definition
        .as_ref()
        .map_or(record.identity.key.as_str(), |node| node.id.as_str())
}
