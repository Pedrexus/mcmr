use super::*;
use serde_json::json;

#[derive(Clone, Copy)]
struct FactFamily(&'static str);

#[derive(Clone, Copy)]
struct RelativePath(&'static str);

struct FactName(&'static str);

fn facts_for(source: &str, family: FactFamily) -> Vec<Value> {
    facts_for_path(RelativePath("example.py"), source, family)
}

fn facts_for_path(relative: RelativePath, source: &str, family: FactFamily) -> Vec<Value> {
    let document = Document {
        relative: relative.0.to_string(),
        source: source.to_string(),
    };
    let mut facts = BTreeMap::from([(family.0.to_string(), Vec::new())]);
    let mut stats = Stats::default();
    extract(
        &document,
        &crate::discovery::Packages::default(),
        &mut facts,
        &mut stats,
    );
    facts.remove(family.0).unwrap_or_default()
}

mod classes;
mod collections;
mod functions;
mod models;
mod names;
