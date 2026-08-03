use super::schema::Schema;
use frames::{
    collect_fact_columns, collect_record_columns, fact_frame, record_frame, value_frame,
};
use polars::prelude::DataFrame;
use serde_json::Value;
use support::{ColumnCatalog, FactRow, RecordRow, ValueRow};
use traversal::Traversal;

mod frames;
mod kind;
mod path;
mod support;
mod traversal;

pub(super) struct Normalized {
    fact_catalog: ColumnCatalog,
    record_catalog: ColumnCatalog,
    facts: Vec<FactRow>,
    records: Vec<RecordRow>,
    values: Vec<ValueRow>,
}

impl Normalized {
    pub(super) fn new(schema: &Schema) -> Self {
        let mut fact_catalog = ColumnCatalog::default();
        let mut record_catalog = ColumnCatalog::default();
        collect_fact_columns(schema, "", &mut fact_catalog);
        collect_record_columns(schema, &mut record_catalog);
        Self {
            fact_catalog,
            record_catalog,
            facts: Vec::new(),
            records: Vec::new(),
            values: Vec::new(),
        }
    }

    pub(super) fn push_fact(
        &mut self,
        fact_order: u64,
        fact: &Value,
        schema: &Schema,
    ) -> Result<(), String> {
        let mut row = FactRow::parse(fact_order, fact)?;
        row.scalars = Traversal {
            fact_order,
            fact_id: &row.fact_id,
            records: &mut self.records,
            values: &mut self.values,
        }
        .root_scalars(schema, fact, &row.fact_id)?;
        self.facts.push(row);
        Ok(())
    }

    pub(super) fn tables(self) -> Result<[DataFrame; 3], String> {
        Ok([
            fact_frame(&self.facts, &self.fact_catalog)?,
            record_frame(&self.records, &self.record_catalog)?,
            value_frame(&self.values)?,
        ])
    }
}
