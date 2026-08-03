use polars::prelude::DataFrame;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;
use serde_json::Value;

use normalization::Normalized;
use schema::compiler::SchemaCompiler;

mod normalization;
mod schema;
mod specialized;

#[pyclass]
pub struct GenericTables {
    facts: DataFrame,
    records: DataFrame,
    values: DataFrame,
}

frame_getters!(GenericTables {
    facts,
    records,
    values,
});

impl GenericTables {
    pub fn attribute_accesses(
        records: &[crate::families::AttributeAccessRecord],
    ) -> Result<Self, String> {
        specialized::attribute_accesses(records)
    }

    pub fn build(facts: &[Value], schema: &str) -> Result<Self, String> {
        let source: Value = serde_json::from_str(schema)
            .map_err(|failure| format!("fact table schema is invalid: {failure}"))?;
        let compiled = SchemaCompiler {
            root: &source,
            resolving: Default::default(),
        }
        .compile(&source)?;
        let mut normalized = Normalized::new(&compiled);
        for (fact_order, fact) in facts.iter().enumerate() {
            normalized.push_fact(fact_order as u64, fact, &compiled)?;
        }
        let [facts, records, values] = normalized.tables()?;
        Ok(Self {
            facts,
            records,
            values,
        })
    }

    pub fn serialized(schema: &str, content: &[u8], source: &str) -> Result<Self, String> {
        let parsed: Value = serde_json::from_slice(content)
            .map_err(|failure| format!("{source} is invalid: {failure}",))?;
        let rows = match parsed {
            Value::Array(rows) => rows,
            row => vec![row],
        };
        Self::build(&rows, schema)
    }

    pub fn string_expressions(
        records: &[crate::families::StringExpressionRecord],
    ) -> Result<Self, String> {
        specialized::string_expressions(records)
    }
}
