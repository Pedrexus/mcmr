use serde::Serialize;

/// Which language declared one symbol, which its identity carries.
///
/// A monorepo names the same thing twice. A `kernel::graph::build` written in Rust and a
/// `mcmr.engine.build` written in Python are different symbols that a shared graph has to keep
/// apart, so the language leads every identity a frontend mints.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Language {
    Python,
    Rust,
    TypeScript,
    C,
    Cpp,
    Cuda,
}

impl Language {
    /// Return the language one path is written in, when this kernel has a frontend for it.
    pub fn of(path: &str) -> Option<Self> {
        match path.rsplit('.').next().unwrap_or_default() {
            "py" | "pyi" => Some(Language::Python),
            "rs" => Some(Language::Rust),
            "ts" | "tsx" | "mts" | "cts" => Some(Language::TypeScript),
            "cu" | "cuh" => Some(Language::Cuda),
            "cpp" | "cc" | "cxx" | "hpp" | "hh" => Some(Language::Cpp),
            "c" | "h" => Some(Language::C),
            _ => None,
        }
    }

    /// Return what this language writes between a holder and the name it holds.
    pub fn separator(self) -> &'static str {
        match self {
            Language::Python | Language::TypeScript => ".",
            Language::Rust | Language::C | Language::Cpp | Language::Cuda => "::",
        }
    }

    pub(crate) fn label(self) -> &'static str {
        match self {
            Language::Python => "python",
            Language::Rust => "rust",
            Language::TypeScript => "typescript",
            Language::C => "c",
            Language::Cpp => "cpp",
            Language::Cuda => "cuda",
        }
    }

    /// Return the language whose namespace this one shares.
    ///
    /// A header, a translation unit, and a CUDA source name each other directly and link into one
    /// program, so a class declared in a header and defined in a `.cpp` is one class rather than
    /// two. Every other language here keeps its own namespace.
    pub(crate) fn namespace(self) -> Self {
        if matches!(self, Language::C | Language::Cuda) {
            Language::Cpp
        } else {
            self
        }
    }
}
