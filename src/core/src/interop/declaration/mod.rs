use super::contracts::{Declaration, Mechanism};
use crate::lexical::CorpusFile;

mod kernel;
mod patterns;

pub(super) use kernel::kernels;
pub(super) use patterns::{DelimitedPattern, IdentifierPattern, after, between};

pub(super) fn native_declarations(file: &CorpusFile, text: &str) -> Vec<Declaration> {
    let mut found = rust_module_declarations(file, text);
    found.extend(cpp_module_declarations(file, text));
    found.extend(kernel_declarations(file, text));
    found
}

fn rust_module_declarations(file: &CorpusFile, text: &str) -> Vec<Declaration> {
    if !file.path.ends_with(".rs") {
        return Vec::new();
    }
    after(
        text,
        IdentifierPattern {
            marker: "#[pymodule]",
            separator: "fn ",
        },
    )
    .map(|name| (name, Mechanism::NativeModule, "rust"))
    .collect()
}

fn cpp_module_declarations(file: &CorpusFile, text: &str) -> Vec<Declaration> {
    if ![".cpp", ".cc", ".cu"]
        .iter()
        .any(|suffix| file.path.ends_with(suffix))
    {
        return Vec::new();
    }
    between(
        text,
        DelimitedPattern {
            marker: "PYBIND11_MODULE(",
            closing: ',',
        },
    )
    .map(|name| (name, Mechanism::NativeModule, "cpp"))
    .collect()
}

fn kernel_declarations(file: &CorpusFile, text: &str) -> Vec<Declaration> {
    if !file.path.ends_with(".cu") && !file.path.ends_with(".cuh") {
        return Vec::new();
    }
    kernels(text)
        .map(|name| (name, Mechanism::Kernel, "cuda"))
        .collect()
}

pub(super) fn shared_library_declarations(file: &CorpusFile, text: &str) -> Vec<Declaration> {
    if !file.path.ends_with(".py") {
        return Vec::new();
    }
    ["CDLL(", "cdll.LoadLibrary("]
        .into_iter()
        .flat_map(|marker| {
            between(
                text,
                DelimitedPattern {
                    marker,
                    closing: ')',
                },
            )
        })
        .map(|name| (name, Mechanism::SharedLibrary, "c"))
        .collect()
}
