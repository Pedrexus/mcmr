use crate::protocol::Stats;
use pyo3::prelude::*;

#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone)]
pub(in crate::bindings) struct SessionStats {
    stats: Stats,
}

impl From<Stats> for SessionStats {
    fn from(stats: Stats) -> Self {
        Self { stats }
    }
}

#[pymethods]
impl SessionStats {
    #[getter]
    fn byte_count(&self) -> usize {
        self.stats.byte_count
    }

    #[getter]
    fn discovery_nanoseconds(&self) -> u64 {
        self.stats.timing.discovery_nanoseconds as u64
    }

    #[getter]
    fn edge_count(&self) -> usize {
        self.stats.graph.edge_count
    }

    #[getter]
    fn extraction_nanoseconds(&self) -> u64 {
        self.stats.timing.extraction_nanoseconds as u64
    }

    #[getter]
    fn fact_count(&self) -> usize {
        self.stats.fact_count
    }

    #[getter]
    fn file_count(&self) -> usize {
        self.stats.file_count
    }

    #[getter]
    fn graph_nanoseconds(&self) -> u64 {
        self.stats.timing.graph_nanoseconds as u64
    }

    #[getter]
    fn node_count(&self) -> usize {
        self.stats.graph.node_count
    }

    #[getter]
    fn parse_failure_count(&self) -> usize {
        self.stats.parse_failure_count
    }

    #[getter]
    fn repository_fingerprint(&self) -> &str {
        &self.stats.repository_fingerprint
    }
}
