use super::request::AnalysisRequest;
use super::stats::SessionStats;
use crate::SessionOutput;
use crate::protocol::Request;
use pending::PendingGenericTable;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

mod pending;
mod selected;

use selected::SelectedFacts;

macro_rules! retained {
    ($records:expr, $families:expr, $family:literal) => {
        $families
            .iter()
            .any(|selected| selected == $family)
            .then_some($records)
    };
}

pub(super) struct SessionState {
    pub(super) selected: SelectedFacts,
    pub(super) generic: BTreeMap<String, PendingGenericTable>,
    pub(super) markers: VecDeque<String>,
    pub(super) stats: SessionStats,
}

impl SessionState {
    pub(super) fn build(mut request: AnalysisRequest) -> Result<Self, String> {
        let kernel_request = request.kernel_request();
        let (mut output, markers) = Self::run(&kernel_request, &request)?;
        let generic = Self::generic_tables(&mut output, request.generic_schemas)?;
        Ok(Self::selected(
            output,
            &request.typed_families,
            generic,
            markers,
        ))
    }

    fn generic_tables(
        output: &mut SessionOutput,
        schemas: BTreeMap<String, String>,
    ) -> Result<BTreeMap<String, PendingGenericTable>, String> {
        schemas
            .into_iter()
            .map(|(family, schema)| {
                let rows = output.generic.remove(&family).ok_or_else(|| {
                    format!("the kernel omitted selected generic family {family}")
                })?;
                Ok((family, PendingGenericTable { rows, schema }))
            })
            .collect()
    }

    fn record_marker(
        markers: &mut VecDeque<String>,
        marked: &mut BTreeSet<String>,
        family: String,
        facts: Vec<Value>,
    ) -> Result<(), String> {
        let marker = family
            .strip_prefix("@typed:")
            .ok_or_else(|| format!("the table session emitted row payloads for {family}"))?;
        if !facts.is_empty() {
            return Err(format!(
                "the table session emitted values with marker {marker}"
            ));
        }
        let marker = marker.to_string();
        if marked.insert(marker.clone()) {
            markers.push_back(marker);
        }
        Ok(())
    }

    fn run(
        kernel_request: &Request,
        request: &AnalysisRequest,
    ) -> Result<(SessionOutput, VecDeque<String>), String> {
        let mut markers = VecDeque::new();
        let mut marked = BTreeSet::new();
        let generic_families = request.generic_schemas.keys().cloned().collect::<Vec<_>>();
        let output = crate::run_session_with_generic(
            kernel_request,
            crate::SessionFamilies {
                typed: &request.typed_families,
                generic: &generic_families,
            },
            |family, facts| Self::record_marker(&mut markers, &mut marked, family, facts),
        )?;
        Ok((output, markers))
    }

    fn selected(
        output: SessionOutput,
        families: &[String],
        generic: BTreeMap<String, PendingGenericTable>,
        markers: VecDeque<String>,
    ) -> Self {
        let attributes = output.facts.attribute_accesses;
        let strings = output.facts.string_expressions;
        Self {
            selected: SelectedFacts {
                functions: retained!(output.facts.functions, families, "FunctionFact"),
                calls: retained!(output.facts.calls, families, "CallFact"),
                classes: retained!(output.facts.classes, families, "ClassFact"),
                import_bindings: retained!(
                    output.facts.import_bindings,
                    families,
                    "ImportBindingFact"
                ),
                syntax: retained!(output.facts.syntax, families, "SyntaxFact"),
                attribute_accesses: retained!(attributes, families, "AttributeAccessFact"),
                string_expressions: retained!(strings, families, "StringExpressionFact"),
            },
            generic,
            markers,
            stats: SessionStats::from(output.stats),
        }
    }
}
