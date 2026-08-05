use super::*;
use serde_json::json;

use fact_family::FactFamily;
use fact_name::FactName;
use relative_path::RelativePath;

mod fact_family;
mod fact_name;
mod relative_path;

fn facts_for<Name: AsRef<str>>(source: &str, family: FactFamily<Name>) -> Vec<Value> {
    facts_for_path(RelativePath("example.py"), source, family)
}

fn facts_for_path<Path: AsRef<str>, Name: AsRef<str>>(
    relative: RelativePath<Path>,
    source: &str,
    family: FactFamily<Name>,
) -> Vec<Value> {
    let document = Document {
        relative: relative.0.as_ref().to_string(),
        source: source.to_string(),
    };
    let family_name = family.0.as_ref();
    let mut facts = BTreeMap::from([(family_name.to_string(), Vec::new())]);
    let mut stats = Stats::default();
    extract(
        &document,
        &crate::discovery::Packages::default(),
        &mut facts,
        &mut stats,
    );
    facts.remove(family_name).unwrap_or_default()
}

mod classes;
mod collections;
mod functions;
mod models;
mod names;
