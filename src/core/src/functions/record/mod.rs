use crate::protocol::Span;
use crate::source::is_test_path;
use serde::Serialize;

mod identity;
mod measures;
mod presentation;
mod semantics;
mod structure;
mod validation;

pub use identity::FunctionIdentity;
pub use measures::FunctionMeasures;
pub use presentation::FunctionPresentation;
pub use semantics::FunctionSemantics;
pub use structure::FunctionStructure;
pub use validation::FunctionValidation;

/// One callable in the language-neutral vocabulary every function rule reads.
#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionRecord {
    #[serde(flatten)]
    pub identity: FunctionIdentity,
    #[serde(flatten)]
    pub presentation: FunctionPresentation,
    #[serde(flatten)]
    pub structure: FunctionStructure,
    #[serde(flatten)]
    pub measures: FunctionMeasures,
    #[serde(flatten)]
    pub semantics: FunctionSemantics,
    #[serde(flatten)]
    pub validation: FunctionValidation,
}

impl FunctionRecord {
    /// Start one record with its provider-guaranteed identity and neutral defaults.
    pub fn new(span: Span, language: &str, name: String) -> Self {
        let key = format!(
            "function:{}:{}:{}:{name}",
            span.path, span.start_line, span.start_column
        );
        let is_test = is_test_path(&span.path);
        Self {
            identity: FunctionIdentity {
                key,
                span,
                language: language.to_string(),
                is_test,
                name,
                ..FunctionIdentity::default()
            },
            ..Self::default()
        }
    }

    /// Serialize one typed provider record for the independent JSON protocol.
    pub fn into_json(self) -> serde_json::Value {
        serde_json::to_value(self).expect("a typed function record must serialize")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn span(line: usize) -> Span {
        Span {
            path: "src/service.rs".to_string(),
            start_line: line,
            start_column: 4,
            end_line: line,
            end_column: 8,
        }
    }

    #[test]
    fn same_named_callables_keep_distinct_fact_identities() {
        let first = FunctionRecord::new(span(3), "rust", "fact".to_string());
        let second = FunctionRecord::new(span(9), "rust", "fact".to_string());

        assert_ne!(first.identity.key, second.identity.key);
        assert_eq!(first.identity.key, "function:src/service.rs:3:4:fact");
    }
}
