mod fact;
mod module_facts;
mod reference_index;

use crate::discovery::{Document, Packages};
use crate::extraction::RecordTargets;
use crate::families;
use crate::functions::FunctionRecord;
use crate::protocol::{JsonObject, Stats};
use crate::source::Source;
use ruff_python_ast::ModModule;
use ruff_python_ast::token::Tokens;
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde_json::Value;
use std::collections::BTreeMap;

use fact::{base, is_test_module};

/// Build every requested fact family from one document, parsing it exactly once.
pub fn extract(
    document: &Document,
    packages: &Packages,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
) {
    extract_into(document, packages, facts, stats, RecordTargets::default());
}

impl RecordTargets<'_> {
    fn extract_all(
        &mut self,
        source: &Source,
        module: &ModModule,
        facts: &mut BTreeMap<String, Vec<Value>>,
    ) {
        self.extract_attribute_accesses(source, module, facts);
        self.extract_calls(source, module, facts);
        self.extract_functions(source, module, facts);
        self.extract_string_expressions(source, module, facts);
    }

    fn extract_functions(
        &mut self,
        source: &Source,
        module: &ModModule,
        facts: &mut BTreeMap<String, Vec<Value>>,
    ) {
        if !facts.contains_key("FunctionFact") && self.functions.is_none() {
            return;
        }
        let records = function_facts(source, module);
        if let Some(stream) = facts.get_mut("FunctionFact") {
            stream.extend(records.iter().cloned().map(FunctionRecord::into_json));
        }
        if let Some(output) = self.functions.as_deref_mut() {
            output.extend(records);
        }
    }

    fn extract_calls(
        &mut self,
        source: &Source,
        module: &ModModule,
        facts: &mut BTreeMap<String, Vec<Value>>,
    ) {
        if !facts.contains_key("CallFact") && self.calls.is_none() {
            return;
        }
        let record = call_fact(source, module);
        if let Some(stream) = facts.get_mut("CallFact") {
            stream.push(record.clone().into_json());
        }
        if let Some(output) = self.calls.as_deref_mut() {
            output.push(record);
        }
    }

    fn extract_attribute_accesses(
        &mut self,
        source: &Source,
        module: &ModModule,
        facts: &mut BTreeMap<String, Vec<Value>>,
    ) {
        if !facts.contains_key("AttributeAccessFact") && self.attribute_accesses.is_none() {
            return;
        }
        let record = families::attribute_accesses(source, module);
        if let Some(stream) = facts.get_mut("AttributeAccessFact") {
            stream.push(record.clone().into_json());
        }
        if let Some(output) = self.attribute_accesses.as_deref_mut() {
            output.push(record);
        }
    }

    fn extract_string_expressions(
        &mut self,
        source: &Source,
        module: &ModModule,
        facts: &mut BTreeMap<String, Vec<Value>>,
    ) {
        if !facts.contains_key("StringExpressionFact") && self.string_expressions.is_none() {
            return;
        }
        let record = families::strings(source, module);
        if let Some(stream) = facts.get_mut("StringExpressionFact") {
            stream.push(record.clone().into_json());
        }
        if let Some(output) = self.string_expressions.as_deref_mut() {
            output.push(record);
        }
    }
}

/// Build requested JSON facts and typed rows from the same Python parse.
pub(crate) fn extract_with_records(
    document: &Document,
    packages: &Packages,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    records: RecordTargets<'_>,
) {
    extract_into(document, packages, facts, stats, records);
}

fn extract_into(
    document: &Document,
    packages: &Packages,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
    mut records: RecordTargets<'_>,
) {
    let parsed = match parse_module(&document.source) {
        Ok(parsed) => parsed,
        Err(_) => {
            stats.parse_failure_count += 1;
            return;
        }
    };
    let source = Source::new(document);
    let module = parsed.syntax();
    deliver_declarations(&source, packages, module, parsed.tokens(), facts);
    records.extract_all(&source, module, facts);
    deliver_documentation(&source, module, parsed.tokens(), facts);
    deliver_families(&source, module, facts);
}

fn deliver_declarations(
    source: &Source,
    packages: &Packages,
    module: &ModModule,
    tokens: &Tokens,
    facts: &mut BTreeMap<String, Vec<Value>>,
) {
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_facts::module_fact(source, module));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(source, packages, module));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(source, module, tokens));
    }
}

fn deliver_documentation(
    source: &Source,
    module: &ModModule,
    tokens: &Tokens,
    facts: &mut BTreeMap<String, Vec<Value>>,
) {
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comment_fact(source, tokens));
    }
    if let Some(stream) = facts.get_mut("WaiverFact") {
        let key = format!("waiverfact:{}", source.relative);
        stream.push(
            JsonObject::new(base(source, &key, module.range()))
                .merged(families::waivers(source, tokens)),
        );
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(crate::syntax::declarations(source, module));
    }
}

fn deliver_families(
    source: &Source,
    module: &ModModule,
    facts: &mut BTreeMap<String, Vec<Value>>,
) {
    for (family, build) in FAMILY_BUILDERS {
        if matches!(*family, "TestFunctionFact" | "TestCaseGroupFact") && !is_test_module(source) {
            continue;
        }
        if let Some(stream) = facts.get_mut(*family) {
            let key = format!("{}:{}", family.to_lowercase(), source.relative);
            stream.push(
                JsonObject::new(base(source, &key, module.range())).merged(build(source, module)),
            );
        }
    }
}

/// Every family whose whole content one file produces from its parsed module.
type FamilyBuilder = fn(&Source, &ModModule) -> Value;
const FAMILY_BUILDERS: &[(&str, FamilyBuilder)] = &[
    ("BranchFact", families::branches),
    ("CollectionFact", families::collections),
    ("ComprehensionFact", families::comprehensions),
    ("Enum", families::enums),
    ("LiteralGroupFact", families::literal_groups),
    ("MethodGroupFact", families::method_groups),
    ("ParameterFact", families::parameters),
    ("ProseSegmentFact", families::prose),
    ("PydanticModelFact", families::pydantic_models),
    ("QueryFact", families::queries),
    ("RuntimeTypeCheckFact", |_, module| {
        families::runtime_checks(module)
    }),
    ("SymbolFact", families::symbols),
    ("TestCaseGroupFact", families::test_case_groups),
    ("TestFunctionFact", families::test_functions),
    ("TryBlockFact", families::try_blocks),
    ("TypeAnnotationFact", families::annotations),
];

mod calls;
mod classes;
mod comments;
mod functions;
pub(crate) mod imports;

pub use functions::function_facts;

use calls::call_fact;
use classes::class_fact;
use comments::comment_fact;
use imports::import_facts;

#[cfg(test)]
mod tests;
