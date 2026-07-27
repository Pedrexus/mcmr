use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// The protocol version a response carries, so a stale binary fails loudly.
pub const VERSION: u32 = 1;

/// One analysis request: where to look, what else to skip, and which fact families to build.
///
/// The exclusions are what this caller adds. Discovery already refuses the directories nothing
/// ever judges, so a caller that says nothing still never reads a dependency tree or a build.
#[derive(Debug, Deserialize)]
pub struct Request {
    pub root: String,
    #[serde(default)]
    pub families: Vec<String>,
    #[serde(default)]
    pub exclude: Vec<String>,
    #[serde(default = "default_suffixes")]
    pub suffixes: Vec<String>,
    #[serde(default)]
    pub graph: bool,
}

/// Read every language this kernel has a frontend for, since a repository rarely holds only one.
///
/// A caller that wants one language still says so, and one that says nothing gets the whole
/// repository, which is the answer a question about how the pieces fit together needs.
///
/// The four inline suffixes are here because a C++ template library keeps its implementations in
/// them. Leaving them out hid 26 files and 18 percent of the lines of one header-only library,
/// which is exactly the half a rule about a function body has to read.
fn default_suffixes() -> Vec<String> {
    [
        ".py", ".pyi", ".rs", ".ts", ".tsx", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
        ".hxx", ".inl", ".ipp", ".tpp", ".cu", ".cuh",
    ]
    .iter()
    .map(|suffix| (*suffix).to_string())
    .collect()
}

/// One analysis response: the requested fact streams and what producing them cost.
#[derive(Debug, Serialize)]
pub struct Response {
    pub version: u32,
    pub facts: BTreeMap<String, Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub graph: Option<crate::graph::Graph>,
    pub stats: Stats,
}

/// What the kernel actually did, so a caller can see the cost it paid.
#[derive(Debug, Default, Serialize)]
pub struct Stats {
    pub file_count: usize,
    pub byte_count: usize,
    pub fact_count: usize,
    pub parse_failure_count: usize,
    pub discovery_nanoseconds: u128,
    pub extraction_nanoseconds: u128,
    pub graph_nanoseconds: u128,
    pub node_count: usize,
    pub edge_count: usize,
}

/// Locate one fact in source, in the shape the Python `SourceSpan` model validates.
#[derive(Clone, Debug, Serialize)]
pub struct Span {
    pub path: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

/// Address one resolved syntax node, in the shape the Python `NodeRef` model validates.
#[derive(Clone, Debug, Serialize)]
pub struct Node {
    pub id: String,
    pub span: Span,
    pub kind: String,
    pub text: String,
}
