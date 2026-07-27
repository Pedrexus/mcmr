use crate::discovery::Scope;
use crate::lexical::Corpus;
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::Path;

/// How far down a manifest or a native source is worth looking for, which is past any layout that
/// declares one and short of the trees a build leaves behind.
const DEPTH: usize = 12;

/// How one language reaches another.
///
/// A repository rarely states these seams anywhere. A Python module spawns a binary a Cargo
/// manifest declares, a native extension is bound by an attribute in Rust or a macro in C++, and a
/// kernel is loaded by name at runtime. Each is a real dependency that no import graph shows, and
/// each breaks silently when one side moves.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Mechanism {
    Binary,
    NativeModule,
    SharedLibrary,
    Kernel,
}

impl Mechanism {
    fn label(self) -> &'static str {
        match self {
            Mechanism::Binary => "binary",
            Mechanism::NativeModule => "native-module",
            Mechanism::SharedLibrary => "shared-library",
            Mechanism::Kernel => "kernel",
        }
    }
}

/// One artifact a repository declares in one language and reaches from another.
#[derive(Clone, Debug, Serialize)]
pub struct Artifact {
    pub name: String,
    pub mechanism: Mechanism,
    pub language: String,
    pub declared_in: String,
    pub referenced_by: Vec<Reference>,
}

/// One place that reaches an artifact, and how sure the kernel is that it does.
#[derive(Clone, Debug, Serialize)]
pub struct Reference {
    pub path: String,
    pub language: String,
    pub line: usize,
    pub is_literal: bool,
}

/// Find every cross-language artifact a repository declares and everything that reaches it.
///
/// Detection is lexical on purpose. These seams live in manifests, attributes, and macros that no
/// single parser covers, and a name stated in one language and spelled in another is exactly the
/// evidence worth having. Every reference records whether the name was a literal, so a rule can
/// weigh a certain match differently from a coincidence.
pub fn scan(root: &Path, scope: &Scope) -> Vec<Artifact> {
    let mut declared: BTreeMap<(String, Mechanism), Artifact> = BTreeMap::new();
    let sources = Corpus::read(root, DEPTH, scope, interesting);
    for (path, text) in sources.files() {
        for (name, mechanism, language) in declarations(path, text) {
            declared
                .entry((name.clone(), mechanism))
                .or_insert_with(|| Artifact {
                    name,
                    mechanism,
                    language: language.to_string(),
                    declared_in: path.clone(),
                    referenced_by: Vec::new(),
                });
        }
    }
    for artifact in declared.values_mut() {
        artifact.referenced_by = sources
            .mentions(&artifact.name, &artifact.declared_in)
            .map(|(path, line)| Reference {
                path: path.to_string(),
                language: language_of(path).to_string(),
                line,
                is_literal: true,
            })
            .collect();
    }
    declared.into_values().collect()
}

/// Whether one file is a manifest or a native source where a seam is declared or crossed.
fn interesting(name: &str) -> bool {
    name.ends_with("Cargo.toml")
        || name.ends_with("package.json")
        || name.ends_with("pyproject.toml")
        || [
            ".rs", ".cpp", ".cc", ".cu", ".cuh", ".h", ".hpp", ".py", ".ts", ".tsx",
        ]
        .iter()
        .any(|suffix| name.ends_with(suffix))
}

fn language_of(path: &str) -> &'static str {
    match path.rsplit('.').next().unwrap_or_default() {
        "rs" => "rust",
        "cu" | "cuh" => "cuda",
        "cpp" | "cc" | "hpp" => "cpp",
        "h" => "c",
        "py" => "python",
        "ts" | "tsx" => "typescript",
        "json" => "manifest",
        _ => "manifest",
    }
}

/// Return every artifact one file declares, by the shape its own language declares them in.
fn declarations(path: &str, text: &str) -> Vec<(String, Mechanism, &'static str)> {
    let mut found = Vec::new();
    let text = text.split("#[cfg(test)]").next().unwrap_or(text);
    if path.ends_with("Cargo.toml") {
        found.extend(binaries(text).map(|name| (name, Mechanism::Binary, "rust")));
    }
    if path.ends_with("pyproject.toml") {
        found.extend(binaries(text).map(|name| (name, Mechanism::Binary, "python")));
    }
    if path.ends_with("package.json") {
        found.extend(node_binaries(text).map(|name| (name, Mechanism::Binary, "typescript")));
    }
    if path.ends_with(".rs") {
        found.extend(
            after(text, "#[pymodule]", "fn ").map(|name| (name, Mechanism::NativeModule, "rust")),
        );
    }
    if path.ends_with(".cpp") || path.ends_with(".cc") || path.ends_with(".cu") {
        found.extend(
            between(text, "PYBIND11_MODULE(", ',')
                .map(|name| (name, Mechanism::NativeModule, "cpp")),
        );
    }
    if path.ends_with(".cu") || path.ends_with(".cuh") {
        found.extend(kernels(text).map(|name| (name, Mechanism::Kernel, "cuda")));
    }
    if path.ends_with(".py") {
        found.extend(
            between(text, "CDLL(", ')')
                .chain(between(text, "cdll.LoadLibrary(", ')'))
                .map(|name| (name, Mechanism::SharedLibrary, "c")),
        );
    }
    found
}

/// Return the binary names one TOML manifest declares, in `[[bin]]` or in `[project.scripts]`.
fn binaries(text: &str) -> impl Iterator<Item = String> + '_ {
    let mut names = Vec::new();
    let mut in_bin = false;
    let mut in_scripts = false;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') {
            in_bin = trimmed == "[[bin]]";
            in_scripts = trimmed == "[project.scripts]";
            continue;
        }
        if in_bin && let Some(name) = value_of(trimmed, "name") {
            names.push(name);
        }
        if in_scripts && let Some((name, _)) = trimmed.split_once('=') {
            names.push(name.trim().trim_matches('"').to_string());
        }
    }
    names.into_iter().filter(|name| !name.is_empty())
}

fn node_binaries(text: &str) -> impl Iterator<Item = String> + '_ {
    let mut names = Vec::new();
    if let Some(section) = text.split_once("\"bin\"") {
        for line in section.1.lines().take(12) {
            if let Some((name, _)) = line.trim().split_once(':') {
                names.push(name.trim().trim_matches('"').to_string());
            }
            if line.contains('}') {
                break;
            }
        }
    }
    names.into_iter().filter(|name| !name.is_empty())
}

fn value_of(line: &str, key: &str) -> Option<String> {
    let (name, value) = line.split_once('=')?;
    (name.trim() == key).then(|| value.trim().trim_matches('"').to_string())
}

/// Return the name of every kernel one CUDA source declares.
fn kernels(text: &str) -> impl Iterator<Item = String> {
    text.match_indices("__global__")
        .filter(|(position, _)| !is_commented(text, *position))
        .filter_map(|(position, marker)| declared_name(&text[position + marker.len()..]))
}

/// Whether one position sits inside a comment rather than in code.
///
/// A note listing the kernels a file holds names `__global__` as often as a declaration does, and
/// reading one of those as a declaration puts a word out of an English sentence into the artifact
/// list. Only a declaration names an artifact, so the text before each marker decides whether the
/// marker is code at all.
fn is_commented(text: &str, position: usize) -> bool {
    let before = &text[..position];
    let line = before.rsplit_once('\n').map_or(before, |(_, tail)| tail);
    if line.contains("//") {
        return true;
    }
    match (before.rfind("/*"), before.rfind("*/")) {
        (Some(opened), closed) => closed.is_none_or(|closed| closed < opened),
        _ => false,
    }
}

/// Return the name one declaration binds, which is the identifier its parameter list opens on.
///
/// Everything between `__global__` and that identifier is something else. The return type sits
/// there, so does another execution space qualifier, so does a launch bound carrying its own
/// parentheses, and so does a template argument list. Reading the first word after the marker
/// answers `void` for almost every kernel ever written, and `void` names nothing a launch could
/// reach, so the name is read from where the parameters start instead.
///
/// A bracketed group is stepped over rather than read, and what stands before it is kept for a
/// template and dropped for a launch bound, because `merge<int>` is named `merge` where
/// `__launch_bounds__(256)` names nothing at all.
fn declared_name(rest: &str) -> Option<String> {
    let mut named = String::new();
    let mut word = String::new();
    let mut held = String::new();
    let mut depth = 0usize;
    for letter in rest.chars() {
        if letter.is_alphanumeric() || letter == '_' {
            word.push(letter);
            continue;
        }
        if !word.is_empty() {
            named = std::mem::take(&mut word);
        }
        match letter {
            '(' if depth == 0 && named != "__launch_bounds__" => {
                return (!named.is_empty()).then_some(named);
            }
            '(' | '<' | '[' => {
                if depth == 0 {
                    held = match letter {
                        '(' => String::new(),
                        _ => named.clone(),
                    };
                }
                depth += 1;
            }
            ')' | '>' | ']' => {
                depth = depth.saturating_sub(1);
                if depth == 0 {
                    named = std::mem::take(&mut held);
                }
            }
            ';' | '{' | '}' if depth == 0 => return None,
            _ => {}
        }
    }
    None
}

/// Return each identifier that follows one marker, which is how an attribute names its subject.
fn after(text: &str, marker: &str, separator: &str) -> impl Iterator<Item = String> {
    text.match_indices(marker).filter_map(move |(position, _)| {
        let rest = &text[position + marker.len()..];
        let start = rest.find(separator)? + separator.len();
        let name: String = rest[start..]
            .chars()
            .skip_while(|letter| letter.is_whitespace())
            .take_while(|letter| letter.is_alphanumeric() || *letter == '_')
            .collect();
        (!name.is_empty()).then_some(name)
    })
}

/// Return each name a macro states as its first argument.
fn between(text: &str, marker: &str, closing: char) -> impl Iterator<Item = String> {
    text.match_indices(marker).filter_map(move |(position, _)| {
        let rest = &text[position + marker.len()..];
        let end = rest.find(closing)?;
        let name = rest[..end].trim().trim_matches('"').to_string();
        (!name.is_empty()).then_some(name)
    })
}

/// Return each artifact as the fact a rule reads.
pub fn facts(artifacts: &[Artifact]) -> Vec<serde_json::Value> {
    artifacts
        .iter()
        .map(|artifact| {
            let languages: std::collections::BTreeSet<&str> = artifact
                .referenced_by
                .iter()
                .map(|reference| reference.language.as_str())
                .collect();
            serde_json::json!({
                "key": format!("interop:{}:{}", artifact.mechanism.label(), artifact.name),
                "span": {"path": artifact.declared_in},
                "language": artifact.language,
                "name": artifact.name,
                "mechanism": artifact.mechanism.label(),
                "declared_language": artifact.language,
                "referencing_languages": languages,
                "references": artifact.referenced_by,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_cargo_manifest_declares_the_binaries_it_ships() {
        let manifest = "[package]\nname = \"kernel\"\n\n[[bin]]\nname = \"mcmr-kernel\"\npath = \"src/main.rs\"\n";

        assert_eq!(binaries(manifest).collect::<Vec<_>>(), vec!["mcmr-kernel"]);
    }

    #[test]
    fn a_project_manifest_declares_its_console_scripts() {
        let manifest =
            "[project.scripts]\nmcmr = \"mcmr.cli:app\"\n\n[tool.ruff]\nline-length = 99\n";

        assert_eq!(binaries(manifest).collect::<Vec<_>>(), vec!["mcmr"]);
    }

    #[test]
    fn a_binding_attribute_names_the_module_it_exports() {
        let source =
            "#[pymodule]\nfn engine(module: &Bound<Module>) -> PyResult<()> {\n    Ok(())\n}\n";

        assert_eq!(
            after(source, "#[pymodule]", "fn ").collect::<Vec<_>>(),
            vec!["engine"]
        );
    }

    #[test]
    fn a_loaded_library_names_the_object_it_opens() {
        let loader = "handle = ctypes.CDLL(\"libfastops.so\")\n";

        assert_eq!(
            between(loader, "CDLL(", ')').collect::<Vec<_>>(),
            vec!["libfastops.so"]
        );
    }

    #[test]
    fn a_pybind_macro_and_a_cuda_kernel_name_themselves() {
        let native = "PYBIND11_MODULE(fastops, module) {\n}\n";
        let kernel = "__global__ void scale(float* data) {}\n";

        assert_eq!(
            between(native, "PYBIND11_MODULE(", ',').collect::<Vec<_>>(),
            vec!["fastops"]
        );
        assert_eq!(kernels(kernel).collect::<Vec<_>>(), vec!["scale"]);
    }

    #[test]
    fn a_kernel_is_named_past_everything_written_between_the_marker_and_its_parameters() {
        let source = concat!(
            "__global__ void scale(float* data) {}\n",
            "__global__ void __launch_bounds__(256, 4) classify_segments(int* out) {}\n",
            "template <typename T>\n__global__ void merge<T>(T* left, T* right) {}\n",
            "__global__ void inline kernels::rank(int* order);\n",
            "extern \"C\" __global__ void __launch_bounds__(128) pack(char* bytes) {}\n",
        );

        assert_eq!(
            kernels(source).collect::<Vec<_>>(),
            vec!["scale", "classify_segments", "merge", "rank", "pack"]
        );
    }

    #[test]
    fn a_marker_with_no_declaration_behind_it_names_nothing() {
        // A qualifier written on a variable and one written on nothing at all both have to answer
        // nothing, since an artifact list is only worth having when every entry is reachable.
        assert!(kernels("__global__ int limit = 4;\n").next().is_none());
        assert!(kernels("__global__\n").next().is_none());
    }

    #[test]
    fn a_note_about_the_kernels_a_file_holds_declares_none_of_them() {
        let source = concat!(
            "// Four __global__ kernels dispatched from the launcher:\n",
            "//   count_thread_kernel -> per document lengths (1 thread each)\n",
            "/* the __global__ ones below take a stream */\n",
            "__global__ void count_thread_kernel(int* out) {}\n",
        );

        assert_eq!(
            kernels(source).collect::<Vec<_>>(),
            vec!["count_thread_kernel"]
        );
    }
}
