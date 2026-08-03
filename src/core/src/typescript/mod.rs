#[cfg(test)]
use crate::discovery::Document;
#[cfg(test)]
use crate::graph::{EdgeKind, Node, NodeKind, ParameterKind, Resolution, Visibility};
#[cfg(test)]
use crate::protocol::Stats;
#[cfg(test)]
use serde_json::Value;
#[cfg(test)]
use std::collections::BTreeMap;

mod callables;
mod facts;
mod graph;
mod support;

pub use facts::{extract, extract_with_functions};
pub use graph::{Located, ResolutionContext, Specifiers, WrittenSpecifier, graph, resolve};

#[cfg(test)]
use graph::{mappings_at, parse_config};

#[cfg(test)]
mod tests;
