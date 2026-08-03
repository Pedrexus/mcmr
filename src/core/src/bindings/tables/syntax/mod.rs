use crate::bindings::frames::located::located_fact;
use crate::syntax::SyntaxRecord;
use facts::syntax_fact_frame;
use nodes::{syntax_child_frame, syntax_node_frame};
use polars::prelude::*;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;

located_fact!(SyntaxRecord);

mod facts;
mod nodes;

#[pyclass]
pub(in crate::bindings) struct SyntaxTables {
    facts: DataFrame,
    nodes: DataFrame,
    children: DataFrame,
}

frame_getters!(SyntaxTables {
    facts,
    nodes,
    children,
});

table_builder!(
    SyntaxTables,
    SyntaxRecord {
        facts: syntax_fact_frame,
        nodes: syntax_node_frame,
        children: syntax_child_frame,
    }
);
