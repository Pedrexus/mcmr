use serde::Deserialize;

/// One analysis request with the root and fact families to build.
#[derive(Debug, Deserialize)]
pub struct Request {
    pub root: String,
    #[serde(default)]
    pub families: Vec<String>,
    #[serde(default = "default_suffixes")]
    pub suffixes: Vec<String>,
    #[serde(default)]
    pub graph: bool,
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub fingerprint_only: bool,
    #[serde(default)]
    pub python_standard_library: Vec<String>,
}

impl Request {
    /// Start one in-process analysis request with the protocol discovery defaults.
    pub fn analysis(root: String, families: Vec<String>) -> Self {
        Self {
            root,
            families,
            suffixes: default_suffixes(),
            graph: false,
            stream: true,
            fingerprint_only: false,
            python_standard_library: Vec::new(),
        }
    }

    /// Return whether this request selected one fact family.
    pub fn wants(&self, family: &str) -> bool {
        self.families.iter().any(|selected| selected == family)
    }
}

/// Read every language frontend when a request does not narrow discovery.
///
/// The inline suffixes matter for C++ template libraries because their implementations commonly
/// live in those files rather than in translation units.
fn default_suffixes() -> Vec<String> {
    [
        ".py", ".pyi", ".rs", ".ts", ".tsx", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
        ".hxx", ".inl", ".ipp", ".tpp", ".cu", ".cuh",
    ]
    .iter()
    .map(|suffix| (*suffix).to_string())
    .collect()
}
