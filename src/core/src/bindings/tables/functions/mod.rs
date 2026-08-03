use crate::bindings::frames::located::LocatedFact;
use crate::functions::FunctionRecord;
use polars::prelude::*;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;

use frames::function_frame;
use relations::{
    control_frame, decorator_frame, function_evidence_frame, parameter_frame, reference_frame,
    tensor_role_frame,
};

mod frames;
mod identity;
mod relations;

impl LocatedFact for FunctionRecord {
    fn key(&self) -> &str {
        &self.identity.key
    }

    fn path(&self) -> &str {
        &self.identity.span.path
    }

    fn start_line(&self) -> u64 {
        self.identity.span.start_line as u64
    }

    fn start_column(&self) -> u64 {
        self.identity.span.start_column as u64
    }

    fn end_line(&self) -> u64 {
        self.identity.span.end_line as u64
    }

    fn end_column(&self) -> u64 {
        self.identity.span.end_column as u64
    }

    fn language(&self) -> &str {
        &self.identity.language
    }
}

#[pyclass]
pub(in crate::bindings) struct FunctionTables {
    functions: DataFrame,
    parameters: DataFrame,
    controls: DataFrame,
    decorators: DataFrame,
    references: DataFrame,
    tensor_roles: DataFrame,
    evidence: DataFrame,
}

frame_getters!(FunctionTables {
    functions,
    parameters,
    controls,
    decorators,
    references,
    tensor_roles,
    evidence,
});

table_builder!(
    FunctionTables,
    FunctionRecord {
        functions: function_frame,
        parameters: parameter_frame,
        controls: control_frame,
        decorators: decorator_frame,
        references: reference_frame,
        tensor_roles: tensor_role_frame,
        evidence: function_evidence_frame,
    }
);
