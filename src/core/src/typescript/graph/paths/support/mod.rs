/// Where one written import specifier lands.
#[derive(Debug, PartialEq, Eq)]
pub enum Located {
    /// A module this repository declares, under the name the whole graph knows it by.
    Module(String),
    /// A package outside this repository, named the way a manifest would install it.
    Package(String),
    /// A path inside this repository that names no module this kernel read.
    Unsettled(String),
}

/// Return one path with the module suffix a specifier may write stripped off it.
///
/// A specifier states `./thing`, `./thing.ts`, or `./thing.js`, and all three name the same module
/// because TypeScript resolves an emitted extension back to the source that produced it. Anything
/// else, such as a `.svelte` or a `.json`, keeps its suffix and settles against nothing.
pub(super) fn without_suffix(path: &str) -> &str {
    const SUFFIXES: &[&str] = &[".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"];
    SUFFIXES
        .iter()
        .find_map(|suffix| path.strip_suffix(suffix))
        .unwrap_or(path)
}

/// Return the package one bare specifier names, which is what a manifest would install.
pub(super) fn package_of(specifier: &str) -> String {
    let parts: Vec<&str> = specifier.split('/').collect();
    let taken = if specifier.starts_with('@') { 2 } else { 1 };
    parts[..taken.min(parts.len())].join("/")
}

pub(super) fn parent_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

/// Return one path with the `.` and `..` steps a specifier writes walked out of it.
pub(super) fn normalized(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for step in path.split('/') {
        match step {
            "" | "." => {}
            ".." => {
                if parts.last().is_some_and(|part| *part != "..") {
                    parts.pop();
                } else {
                    parts.push("..");
                }
            }
            name => parts.push(name),
        }
    }
    parts.join("/")
}

pub(in crate::typescript::graph) fn split_import(expression: &str) -> (&str, &str) {
    expression.rsplit_once('.').unwrap_or((expression, ""))
}
