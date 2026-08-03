use crate::calls::CallRecord;
use crate::comments;
use crate::discovery::Document;
use crate::extraction::RecordTargets;
use crate::functions::FunctionRecord;
use crate::protocol::Stats;
use crate::source::Source;
use serde_json::Value;
use std::collections::BTreeMap;

/// Build every requested fact family from one Rust document.
///
/// The families are the ones every frontend fills, because a general rule reads the same fact
/// whichever language produced it. Rust spells the shared ideas its own way: `pub` is the
/// visibility keyword, an `impl` block holds the methods of the type it names, a trait is the
/// contract a type implements, and `use` is the import.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    extract_into(document, facts, stats, RecordTargets::default());
}

/// Build requested JSON facts and typed rows from the same Rust parse.
pub(crate) fn extract_with_records(
    document: &Document,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    records: RecordTargets<'_>,
) {
    extract_into(document, facts, stats, records);
}

fn extract_into(
    document: &Document,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    mut records: RecordTargets<'_>,
) {
    let Ok(parsed) = syn::parse_file(&document.source) else {
        stats.parse_failure_count += 1;
        return;
    };
    let source = Source::new(document);
    deliver_structure(&source, &parsed, facts);
    deliver_functions(&source, &parsed, facts, records.functions.as_deref_mut());
    deliver_calls(&source, &parsed, facts, records.calls.as_deref_mut());
    deliver_documentation(&source, &parsed, facts);
}

fn deliver_structure(
    source: &Source,
    parsed: &syn::File,
    facts: &mut BTreeMap<String, Vec<Value>>,
) {
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_fact(source, parsed));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(source, parsed));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(source, parsed));
    }
    if let Some(stream) = facts.get_mut("RustSurfaceFact") {
        stream.push(surface_fact(source, parsed));
    }
}

fn deliver_documentation(
    source: &Source,
    parsed: &syn::File,
    facts: &mut BTreeMap<String, Vec<Value>>,
) {
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comments::fact(
            source,
            "rust",
            scan(&source.text),
            &mut Notes,
        ));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(syntax_facts(source, parsed));
    }
}

fn deliver_functions(
    source: &Source,
    parsed: &syn::File,
    facts: &mut BTreeMap<String, Vec<Value>>,
    output: Option<&mut Vec<FunctionRecord>>,
) {
    if !facts.contains_key("FunctionFact") && output.is_none() {
        return;
    }
    let records = function_facts(source, parsed);
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(records.iter().cloned().map(FunctionRecord::into_json));
    }
    if let Some(output) = output {
        output.extend(records);
    }
}

fn deliver_calls(
    source: &Source,
    parsed: &syn::File,
    facts: &mut BTreeMap<String, Vec<Value>>,
    output: Option<&mut Vec<CallRecord>>,
) {
    if !facts.contains_key("CallFact") && output.is_none() {
        return;
    }
    let record = call_fact(source, parsed);
    if let Some(stream) = facts.get_mut("CallFact") {
        stream.push(record.clone().into_json());
    }
    if let Some(output) = output {
        output.push(record);
    }
}

mod calls;
mod classes;
mod comment_facts;
mod functions;
mod graph;
mod module;
mod ownership;
mod resolution;
mod support;
mod syntax;

pub use functions::function_facts;
pub use graph::graph;
pub(crate) use resolution::resolve;

use calls::call_fact;
use classes::class_fact;
use comment_facts::{Notes, scan};
use module::{import_facts, module_fact};
use ownership::surface_fact;
use syntax::syntax_facts;

#[cfg(test)]
use graph::Collector;

#[cfg(test)]
mod tests;
