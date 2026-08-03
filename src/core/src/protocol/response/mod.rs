use super::stats::Stats;
use serde::Serialize;
use std::collections::BTreeMap;

/// One analysis response with the requested facts and measured work.
#[derive(Debug, Serialize)]
pub struct Response {
    pub version: u32,
    pub facts: BTreeMap<String, Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub graph: Option<crate::graph::Graph>,
    pub stats: Stats,
}
