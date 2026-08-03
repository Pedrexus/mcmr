use crate::calls::CallRecord;
use crate::comments;
use crate::discovery::Document;
use crate::extraction::RecordTargets;
use crate::functions::FunctionRecord;
use crate::protocol::Stats;
use crate::source::Source;
use serde_json::Value;
use std::collections::BTreeMap;
use tree_sitter::Node as Syntax;

/// Build every requested fact family from one C, C++, or CUDA document.
///
/// These three are one frontend because they are one language with three dialects. A header
/// declares what a translation unit defines, a CUDA source is C++ with kernels added, and all
/// three link into one program where a name means one thing. What differs is small enough to be a
/// few branches: `static` is how C narrows a name, an access specifier is how C++ does it, and a
/// kernel is a function with an execution space written in front of it.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    extract_into(document, facts, stats, RecordTargets::default());
}

/// Build requested JSON facts and typed rows from the same native-language parse.
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
    let language = language(&document.relative);
    let source = Source::new(document);
    let Some(tree) = parse(&source) else {
        stats.parse_failure_count += 1;
        return;
    };
    let unit = Unit { source, language };
    let root = tree.root_node();
    deliver_structure(&unit, root, facts);
    deliver_functions(&unit, root, facts, records.functions.as_deref_mut());
    deliver_calls(&unit, root, facts, records.calls.as_deref_mut());
    deliver_documentation(&unit, root, facts);
}

fn deliver_structure(unit: &Unit, root: Syntax<'_>, facts: &mut BTreeMap<String, Vec<Value>>) {
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(unit.module_fact(root));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(unit.import_facts(root));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(unit.class_fact(root));
    }
    if let Some(stream) = facts.get_mut("KernelLaunchFact") {
        stream.extend(unit.launch_facts(root));
    }
}

fn deliver_documentation(unit: &Unit, root: Syntax<'_>, facts: &mut BTreeMap<String, Vec<Value>>) {
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comments::fact(
            &unit.source,
            dialect(unit.language),
            walk(root)
                .into_iter()
                .filter(|node| node.kind() == "comment")
                .map(|node| comments::at(node.start_byte()..node.end_byte())),
            &mut Notes::of(&unit.source.relative),
        ));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(unit.syntax_facts(root));
    }
}

fn deliver_functions(
    unit: &Unit,
    root: Syntax<'_>,
    facts: &mut BTreeMap<String, Vec<Value>>,
    output: Option<&mut Vec<FunctionRecord>>,
) {
    if !facts.contains_key("FunctionFact") && output.is_none() {
        return;
    }
    let records = unit.function_facts(root);
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(records.iter().cloned().map(FunctionRecord::into_json));
    }
    if let Some(output) = output {
        output.extend(records);
    }
}

fn deliver_calls(
    unit: &Unit,
    root: Syntax<'_>,
    facts: &mut BTreeMap<String, Vec<Value>>,
    output: Option<&mut Vec<CallRecord>>,
) {
    if !facts.contains_key("CallFact") && output.is_none() {
        return;
    }
    let record = unit.call_fact(root);
    if let Some(stream) = facts.get_mut("CallFact") {
        stream.push(record.clone().into_json());
    }
    if let Some(output) = output {
        output.push(record);
    }
}

mod comment_facts;
mod graph;
mod parsing;
mod resolution;
mod support;
mod unit;

pub use graph::graph;
pub use parsing::reads;
pub use resolution::{Lookup, resolve};

use comment_facts::Notes;
use parsing::{language, parse};
use support::{dialect, walk};
use unit::Unit;

#[cfg(test)]
use graph::HeaderPath;

#[cfg(test)]
mod tests;
