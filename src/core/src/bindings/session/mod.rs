use super::generic_tables::GenericTables;
use super::tables::{CallTables, ClassTables, FunctionTables, ImportBindingTables, SyntaxTables};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyString;
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::{Mutex, MutexGuard};

use request::AnalysisRequest;
use state::SessionState;
pub(in crate::bindings) use stats::SessionStats;

mod request;
mod state;
mod stats;

macro_rules! analysis_session_methods {
    ($($method:ident, $tables:ty, $family:literal, $field:ident, $build:path);+ $(;)?) => {
        #[pymethods]
        impl AnalysisSession {
            #[new]
            #[pyo3(signature = (root, typed_families, *, python_standard_library, suffixes=None, generic_schemas=None))]
            fn new(
                root: PathBuf,
                typed_families: Vec<String>,
                python_standard_library: Vec<String>,
                suffixes: Option<Vec<String>>,
                generic_schemas: Option<BTreeMap<String, String>>,
            ) -> PyResult<Self> {
                let request = AnalysisRequest {
                    root,
                    typed_families,
                    python_standard_library,
                    suffixes,
                    generic_schemas: generic_schemas.unwrap_or_default(),
                };
                let state = Python::attach(|py| py.detach(|| SessionState::build(request)))
                    .map_err(PyRuntimeError::new_err)?;
                Ok(Self {
                    state: Mutex::new(state),
                })
            }

            $(
                fn $method(&self, py: Python<'_>) -> PyResult<$tables> {
                    self.release(py, $family, |state| &mut state.selected.$field, $build)
                }
            )+

            /// Move one schema-normalized family into its universal FACTS, RECORDS, and VALUES frames.
            fn table(&self, py: Python<'_>, family: &str) -> PyResult<GenericTables> {
                if family == "AttributeAccessFact"
                    && self.lock()?.selected.attribute_accesses.is_some()
                {
                    return self.release(
                        py,
                        family,
                        |state| &mut state.selected.attribute_accesses,
                        GenericTables::attribute_accesses,
                    );
                }
                if family == "StringExpressionFact"
                    && self.lock()?.selected.string_expressions.is_some()
                {
                    return self.release(
                        py,
                        family,
                        |state| &mut state.selected.string_expressions,
                        GenericTables::string_expressions,
                    );
                }
                let pending = self.lock()?.generic.remove(family).ok_or_else(|| {
                    PyRuntimeError::new_err(format!(
                        "{family} table was not selected or was released"
                    ))
                })?;
                py.detach(move || GenericTables::build(&pending.rows, &pending.schema))
                    .map_err(PyRuntimeError::new_err)
            }

            /// Move the next selected table family marker out of the session.
            fn next_table_marker(&self) -> PyResult<Option<String>> {
                Ok(self.lock()?.markers.pop_front())
            }

            fn stats(&self) -> PyResult<SessionStats> {
                Ok(self.lock()?.stats.clone())
            }
        }
    };
}

#[pyclass]
pub(in crate::bindings) struct AnalysisSession {
    state: Mutex<SessionState>,
}

analysis_session_methods!(
    function_tables, FunctionTables, "function", functions, FunctionTables::build;
    call_tables, CallTables, "call", calls, CallTables::build;
    class_tables, ClassTables, "class", classes, ClassTables::build;
    import_binding_tables, ImportBindingTables, "import binding", import_bindings, ImportBindingTables::build;
    syntax_tables, SyntaxTables, "syntax", syntax, SyntaxTables::build;
);

impl AnalysisSession {
    fn lock(&self) -> PyResult<MutexGuard<'_, SessionState>> {
        self.state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("the analysis session lock was poisoned"))
    }

    fn release<Row: Send, Tables: Send>(
        &self,
        py: Python<'_>,
        family: &str,
        selected: fn(&mut SessionState) -> &mut Option<Vec<Row>>,
        build: fn(&[Row]) -> Result<Tables, String>,
    ) -> PyResult<Tables> {
        let records = {
            let mut state = self.lock()?;
            selected(&mut state).take().ok_or_else(|| {
                PyRuntimeError::new_err(format!(
                    "{family} tables were not selected or were already released"
                ))
            })?
        };
        py.detach(move || build(&records))
            .map_err(PyRuntimeError::new_err)
    }
}

#[pyfunction(signature = (facts, *, schema))]
pub(in crate::bindings) fn fact_tables(
    py: Python<'_>,
    facts: String,
    schema: &Bound<'_, PyString>,
) -> PyResult<GenericTables> {
    let schema = schema.to_str()?.to_string();
    py.detach(move || GenericTables::serialized(&schema, facts.as_bytes(), "in-memory fact table"))
        .map_err(PyRuntimeError::new_err)
}
