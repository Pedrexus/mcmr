use crate::comments;
use crate::discovery::Document;
use crate::functions::FunctionRecord;
use crate::protocol::Stats;
use crate::source::Source;
use declarations::{class_fact, function_facts};
use module::{import_facts, module_fact};
use notes::Notes;
use oxc_allocator::Allocator;
use oxc_parser::Parser;
use oxc_span::SourceType;
use serde_json::Value;
use std::collections::BTreeMap;
use surface::surface;
use syntax::syntax_facts;

mod declarations;
mod module;
mod notes;
mod surface;
mod syntax;

/// Build every requested fact family from one TypeScript document.
///
/// The families are the same ones the Python frontend fills, because a general rule reads the same
/// fact whichever language produced it. Only the spelling of a declaration differs: `export` is
/// the visibility keyword, a method sits in a class body, and an import names a path rather than a
/// package.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    extract_into(document, facts, stats, None);
}

/// Build requested JSON facts and typed function rows from the same TypeScript parse.
pub fn extract_with_functions(
    document: &Document,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    functions: &mut Vec<FunctionRecord>,
) {
    extract_into(document, facts, stats, Some(functions));
}

fn extract_into(
    document: &Document,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    functions: Option<&mut Vec<FunctionRecord>>,
) {
    let allocator = Allocator::default();
    let kind = SourceType::from_path(&document.relative)
        .expect("the TypeScript frontend must receive a supported source suffix");
    let parsed = Parser::new(&allocator, &document.source, kind).parse();
    if parsed.panicked {
        stats.parse_failure_count += 1;
        return;
    }
    let source = Source::new(document);
    let program = &parsed.program;
    emit_all(document, &source, program, facts, functions);
}

fn emit_all(
    document: &Document,
    source: &Source,
    program: &oxc_ast::ast::Program,
    facts: &mut FactStreams,
    functions: Option<&mut Vec<FunctionRecord>>,
) {
    emit_module(source, program, facts);
    emit_imports(source, program, facts);
    emit_functions(source, program, facts, functions);
    emit_class(source, program, facts);
    emit_surface(source, program, facts);
    emit_comments(document, source, program, facts);
    emit_syntax(source, program, facts);
}

fn emit_class(source: &Source, program: &oxc_ast::ast::Program, facts: &mut FactStreams) {
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(source, program));
    }
}

fn emit_comments(
    document: &Document,
    source: &Source,
    program: &oxc_ast::ast::Program,
    facts: &mut FactStreams,
) {
    let Some(stream) = facts.get_mut("CommentFact") else {
        return;
    };
    stream.push(comments::fact(
        source,
        "typescript",
        program
            .comments
            .iter()
            .map(|comment| comments::at(comment.span.start as usize..comment.span.end as usize)),
        &mut Notes {
            relative: document.relative.clone(),
        },
    ));
}

fn emit_functions(
    source: &Source,
    program: &oxc_ast::ast::Program,
    facts: &mut FactStreams,
    functions: Option<&mut Vec<FunctionRecord>>,
) {
    if !facts.contains_key("FunctionFact") && functions.is_none() {
        return;
    }
    let records = function_facts(source, program);
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(records.iter().cloned().map(FunctionRecord::into_json));
    }
    if let Some(output) = functions {
        output.extend(records);
    }
}

fn emit_imports(source: &Source, program: &oxc_ast::ast::Program, facts: &mut FactStreams) {
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(source, program));
    }
}

fn emit_module(source: &Source, program: &oxc_ast::ast::Program, facts: &mut FactStreams) {
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_fact(source, program));
    }
}

fn emit_surface(source: &Source, program: &oxc_ast::ast::Program, facts: &mut FactStreams) {
    if let Some(stream) = facts.get_mut("ModuleSurfaceFact") {
        stream.push(surface(source, program));
    }
}

fn emit_syntax(source: &Source, program: &oxc_ast::ast::Program, facts: &mut FactStreams) {
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(syntax_facts(source, program));
    }
}

type FactStreams = BTreeMap<String, Vec<Value>>;
