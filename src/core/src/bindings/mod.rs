use generic_tables::GenericTables;
use pyo3::prelude::*;

use session::{AnalysisSession, SessionStats, fact_tables};
use tables::{CallTables, ClassTables, FunctionTables, ImportBindingTables, SyntaxTables};

macro_rules! frame_getters {
    ($owner:ident { $($field:ident),+ $(,)? }) => {
        #[pymethods]
        impl $owner {
            fn frames<'py>(
                &mut self,
                py: Python<'py>,
            ) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
                let frames = pyo3::types::PyDict::new(py);
                $(
                    frames.set_item(
                        stringify!($field),
                        PyDataFrame(std::mem::take(&mut self.$field)),
                    )?;
                )+
                Ok(frames)
            }

            $(
                #[getter]
                fn $field(&mut self) -> PyDataFrame {
                    PyDataFrame(std::mem::take(&mut self.$field))
                }
            )+
        }
    };
}

macro_rules! table_builder {
    ($owner:ident, $record:ty { $($field:ident: $builder:path),+ $(,)? }) => {
        impl $owner {
            pub(in crate::bindings) fn build(records: &[$record]) -> Result<Self, String> {
                Ok(Self {
                    $(
                        $field: $crate::bindings::frames::frame_result($builder(records))?,
                    )+
                })
            }
        }
    };
}

mod contextual;
mod frames;
mod generic_tables;
mod relations;
mod rows;
mod session;
mod tables;

#[pymodule(gil_used = false)]
fn kernel_tables(module: &Bound<'_, PyModule>) -> PyResult<()> {
    register_table_classes(module)?;
    register_support_classes(module)?;
    Ok(())
}

fn register_table_classes(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<AnalysisSession>()?;
    module.add_class::<FunctionTables>()?;
    module.add_class::<CallTables>()?;
    module.add_class::<ClassTables>()?;
    module.add_class::<ImportBindingTables>()?;
    module.add_class::<SyntaxTables>()?;
    Ok(())
}

fn register_support_classes(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<GenericTables>()?;
    module.add_class::<contextual::GlinerClassifier>()?;
    module.add_class::<SessionStats>()?;
    module.add_function(wrap_pyfunction!(fact_tables, module)?)?;
    Ok(())
}
