use gliner2::config::{ExtractorConfig, ModelFiles};
use gliner2::{CandleExtractor, ExtractOptions, SchemaTransformer};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyString;
use serde_json::Value;
use std::path::{Path, PathBuf};

fn runtime_error(error: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(error.to_string())
}

#[pyclass(frozen)]
pub struct GlinerClassifier {
    extractor: CandleExtractor,
    transformer: SchemaTransformer,
}

#[pymethods]
impl GlinerClassifier {
    #[new]
    fn new(model_dir: PathBuf) -> PyResult<Self> {
        let files = model_files(&model_dir);
        let config = extractor_config(&files)?;
        let transformer = schema_transformer(&files)?;
        let vocabulary_size = transformer.tokenizer.get_vocab_size(true);
        let extractor =
            CandleExtractor::load_cpu(&files, config, vocabulary_size).map_err(runtime_error)?;
        Ok(Self {
            extractor,
            transformer,
        })
    }

    #[pyo3(signature = (texts, task, *, labels, batch_size))]
    fn classify(
        &self,
        py: Python<'_>,
        texts: Vec<String>,
        task: String,
        labels: &Bound<'_, PyString>,
        batch_size: usize,
    ) -> PyResult<String> {
        let labels = labels.to_str()?.to_string();
        py.detach(move || {
            let labels: Value = serde_json::from_str(&labels).map_err(runtime_error)?;
            let options = ExtractOptions {
                include_confidence: true,
                batch_size,
                ..ExtractOptions::default()
            };
            let results = self
                .extractor
                .batch_classify_text(&self.transformer, &texts, &task, labels, &options)
                .map_err(runtime_error)?;
            serde_json::to_string(&results).map_err(runtime_error)
        })
    }
}

fn extractor_config(files: &ModelFiles) -> PyResult<ExtractorConfig> {
    let content = std::fs::read_to_string(&files.config).map_err(runtime_error)?;
    serde_json::from_str(&content).map_err(runtime_error)
}

fn model_files(model_dir: &Path) -> ModelFiles {
    ModelFiles {
        config: model_dir.join("config.json"),
        encoder_config: model_dir.join("encoder_config/config.json"),
        tokenizer: model_dir.join("tokenizer.json"),
        weights: model_dir.join("model.safetensors"),
    }
}

fn schema_transformer(files: &ModelFiles) -> PyResult<SchemaTransformer> {
    let tokenizer = files
        .tokenizer
        .to_str()
        .ok_or_else(|| PyRuntimeError::new_err("GLiNER2 tokenizer path is not UTF-8"))?;
    SchemaTransformer::new(tokenizer).map_err(runtime_error)
}
