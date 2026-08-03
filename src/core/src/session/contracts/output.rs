use super::facts::SessionFacts;
use crate::protocol::Stats;
use std::collections::BTreeMap;

/// One in-process analysis result beside the legacy batches emitted during the same parse.
#[derive(Default)]
pub struct SessionOutput {
    pub facts: SessionFacts,
    pub generic: BTreeMap<String, Vec<serde_json::Value>>,
    pub stats: Stats,
}
