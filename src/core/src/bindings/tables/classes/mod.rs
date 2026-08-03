use crate::bindings::frames::located::located_fact;
use crate::classes::ClassRecord;
use groups::{ClassCoreFrames, ClassRepositoryFrames, ClassValueFrames};
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;

mod core;
mod groups;
mod repository;
mod values;

located_fact!(ClassRecord);

#[pyclass]
pub(in crate::bindings) struct ClassTables {
    core: ClassCoreFrames,
    values: ClassValueFrames,
    repository: ClassRepositoryFrames,
}

macro_rules! grouped_frame_getters {
    ($($group:ident { $($field:ident),+ $(,)? }),+ $(,)?) => {
        #[pymethods]
        impl ClassTables {
            fn frames<'py>(
                &mut self,
                py: Python<'py>,
            ) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
                let frames = pyo3::types::PyDict::new(py);
                $($(frames.set_item(
                    stringify!($field),
                    PyDataFrame(std::mem::take(&mut self.$group.$field)),
                )?;)+)+
                Ok(frames)
            }

            $($(
                #[getter]
                fn $field(&mut self) -> PyDataFrame {
                    PyDataFrame(std::mem::take(&mut self.$group.$field))
                }
            )+)+
        }
    };
}

grouped_frame_getters!(
    core {
        facts,
        classes,
        methods,
        evidence
    },
    values {
        direct_bases,
        class_decorators,
        class_keywords,
        direct_subclasses,
        importing_modules,
        method_decorators,
        owner_qualified_calls,
    },
    repository {
        coupled_groups,
        coupled_group_suffixes,
        model_files,
        projections,
        projection_attributes,
        projection_output_keys,
    },
);

impl ClassTables {
    pub(in crate::bindings) fn build(records: &[ClassRecord]) -> Result<Self, String> {
        Ok(Self {
            core: ClassCoreFrames::build(records)?,
            values: ClassValueFrames::build(records)?,
            repository: ClassRepositoryFrames::build(records)?,
        })
    }
}
