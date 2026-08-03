use crate::graph::Language;
use crate::source::Source;
use tree_sitter::{Parser, Tree};

/// Whether this frontend reads one file, which is every dialect and every inline implementation.
///
/// A C++ template library keeps its bodies in `.inl`, `.ipp`, and `.tpp` rather than in a
/// translation unit, and those are exactly the files a rule about a function body has to read.
/// Leaving them out hid 26 files and 18 percent of the lines of one header-only library. The
/// graph's language map names the six languages that carry node identity and knows none of them,
/// so the frontend states which suffixes its own grammars accept.
pub fn reads(relative: &str) -> bool {
    matches!(
        relative.rsplit('.').next().unwrap_or_default(),
        "c" | "h"
            | "cc"
            | "cpp"
            | "cxx"
            | "hpp"
            | "hh"
            | "hxx"
            | "inl"
            | "ipp"
            | "tpp"
            | "cu"
            | "cuh"
    )
}

/// Return the graph language one supported native suffix declares.
pub(super) fn language(relative: &str) -> Language {
    match relative.rsplit('.').next().unwrap_or_default() {
        "cu" | "cuh" => Language::Cuda,
        "c" | "h" => Language::C,
        "cc" | "cpp" | "cxx" | "hpp" | "hh" | "hxx" | "inl" | "ipp" | "tpp" => Language::Cpp,
        _ => panic!("the native frontend must receive a supported source suffix"),
    }
}

/// Parse one translation unit with the grammar its own dialect is written in.
///
/// CUDA is the one that matters. Its grammar extends the C++ one with the execution space
/// qualifiers and the launch bracket, so `__global__`, `__shared__`, and
/// `kernel<<<grid, block>>>(...)` arrive as real nodes rather than as syntax the parser recovered
/// around, which is the difference between reading a launch and guessing at one.
///
/// A `.h` is read as C++ whatever its project calls itself. A header cannot say which of the two
/// languages wrote it, and the C++ grammar reads a C header correctly while the C grammar reads a
/// class as an error.
pub(super) fn parse(source: &Source) -> Option<Tree> {
    let mut parser = Parser::new();
    parser.set_language(&grammar(&source.relative)).ok()?;
    parser.parse(&source.text, None)
}

/// Return the grammar one file's own dialect is written in.
pub(super) fn grammar(relative: &str) -> tree_sitter::Language {
    match relative.rsplit('.').next().unwrap_or_default() {
        "cu" | "cuh" => tree_sitter_cuda::LANGUAGE.into(),
        "c" => tree_sitter_c::LANGUAGE.into(),
        _ => tree_sitter_cpp::LANGUAGE.into(),
    }
}
