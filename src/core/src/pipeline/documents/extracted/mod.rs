use self::rows::ExtractedRows;
use super::selection::ExtractionSelection;
use crate::protocol::Stats;
use crate::{
    classes, discovery, extraction, graph, imports, native, python, rust, syntax, typescript,
};
use serde_json::Value;
use std::collections::BTreeMap;

mod rows;

/// Facts and typed rows extracted from one source document.
pub(super) struct ExtractedDocument {
    pub(super) facts: BTreeMap<String, Vec<Value>>,
    pub(super) rows: ExtractedRows,
    pub(super) stats: Stats,
}

impl ExtractedDocument {
    pub(super) fn of(
        document: &discovery::Document,
        packages: &discovery::Packages,
        families: &[String],
        selected: ExtractionSelection,
    ) -> Result<Self, String> {
        let mut extracted = Self::empty(families);
        extracted.run_frontend(document, packages, selected);
        extracted.convert_legacy(selected)?;
        Ok(extracted)
    }

    fn converted<Record>(
        values: Vec<Value>,
        convert: impl FnMut(Value) -> Result<Record, String>,
    ) -> Result<Vec<Record>, String> {
        values.into_iter().map(convert).collect()
    }

    fn empty(families: &[String]) -> Self {
        Self {
            facts: families
                .iter()
                .map(|family| (family.clone(), Vec::new()))
                .collect(),
            rows: ExtractedRows::default(),
            stats: Stats::default(),
        }
    }

    fn convert_legacy(&mut self, selected: ExtractionSelection) -> Result<(), String> {
        let syntax = self.selected_values(
            "SyntaxFact",
            selected
                .families
                .syntax
                .then_some(selected.retention.syntax),
        );
        self.rows.syntax = Self::converted(syntax, syntax::SyntaxRecord::from_json)?;
        let classes = self.selected_values(
            "ClassFact",
            selected
                .families
                .classes
                .then_some(selected.retention.classes),
        );
        self.rows.classes = Self::converted(classes, classes::ClassRecord::from_json)?;
        let imports = self.selected_values(
            "ImportBindingFact",
            selected
                .families
                .import_bindings
                .then_some(selected.retention.import_bindings),
        );
        self.rows.import_bindings =
            Self::converted(imports, imports::ImportBindingRecord::from_json)?;
        Ok(())
    }

    fn run_frontend(
        &mut self,
        document: &discovery::Document,
        packages: &discovery::Packages,
        selected: ExtractionSelection,
    ) {
        match graph::Language::of(&document.relative) {
            Some(graph::Language::TypeScript) if selected.families.functions => {
                typescript::extract_with_functions(
                    document,
                    &mut self.facts,
                    &mut self.stats,
                    &mut self.rows.functions,
                )
            }
            Some(graph::Language::TypeScript) => {
                typescript::extract(document, &mut self.facts, &mut self.stats)
            }
            Some(graph::Language::Rust) => rust::extract_with_records(
                document,
                &mut self.facts,
                &mut self.stats,
                extraction::RecordTargets {
                    functions: selected
                        .families
                        .functions
                        .then_some(&mut self.rows.functions),
                    calls: selected.families.calls.then_some(&mut self.rows.calls),
                    ..Default::default()
                },
            ),
            _ if native::reads(&document.relative) => native::extract_with_records(
                document,
                &mut self.facts,
                &mut self.stats,
                extraction::RecordTargets {
                    functions: selected
                        .families
                        .functions
                        .then_some(&mut self.rows.functions),
                    calls: selected.families.calls.then_some(&mut self.rows.calls),
                    ..Default::default()
                },
            ),
            _ => python::extract_with_records(
                document,
                packages,
                &mut self.facts,
                &mut self.stats,
                extraction::RecordTargets {
                    functions: selected
                        .families
                        .functions
                        .then_some(&mut self.rows.functions),
                    calls: selected.families.calls.then_some(&mut self.rows.calls),
                    attribute_accesses: selected
                        .families
                        .attribute_accesses
                        .then_some(&mut self.rows.attribute_accesses),
                    string_expressions: selected
                        .families
                        .string_expressions
                        .then_some(&mut self.rows.string_expressions),
                },
            ),
        }
    }

    fn selected_values(&mut self, family: &str, retain: Option<bool>) -> Vec<Value> {
        match retain {
            Some(true) => self.facts.get(family).cloned().unwrap_or_default(),
            Some(false) => self.facts.remove(family).unwrap_or_default(),
            None => Vec::new(),
        }
    }
}
