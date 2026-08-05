use crate::discovery::Scope;
use crate::lexical::{Corpus, CorpusFile, Mention};
use std::collections::BTreeMap;
use std::path::Path;

mod contracts;
mod declaration;
mod manifest;

use contracts::{Artifact, Declaration, Mechanism, Reference};
#[cfg(test)]
use declaration::{DelimitedPattern, IdentifierPattern, after, between, kernels};
use declaration::{native_declarations, shared_library_declarations};
use manifest::manifest_declarations;
#[cfg(test)]
use manifest::{binaries, console_scripts, node_binaries};

/// Find every cross-language artifact a repository declares and everything that reaches it.
///
/// Detection is lexical on purpose. These seams live in manifests, attributes, and macros that no
/// single parser covers, and a name stated in one language and spelled in another is exactly the
/// evidence worth having. Every reference records whether the name was a literal, so a rule can
/// weigh a certain match differently from a coincidence.
pub(crate) fn scan(root: &Path, scope: &Scope) -> Result<Vec<Artifact>, String> {
    let mut declared: BTreeMap<(String, Mechanism), Artifact> = BTreeMap::new();
    let sources = Corpus::read(root, scope, interesting)?;
    for file in sources.files() {
        for (name, mechanism, language) in declarations(file)? {
            declared
                .entry((name.clone(), mechanism))
                .or_insert_with(|| Artifact {
                    name,
                    mechanism,
                    language: language.to_string(),
                    declared_in: file.path.clone(),
                    referenced_by: Vec::new(),
                });
        }
    }
    for artifact in declared.values_mut() {
        artifact.referenced_by = sources
            .mentions(Mention {
                name: &artifact.name,
                declared_in: &artifact.declared_in,
            })
            .map(|(path, line)| Reference {
                path: path.to_string(),
                language: language_of(path).to_string(),
                line,
            })
            .collect();
    }
    Ok(declared.into_values().collect())
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
fn declarations(file: &CorpusFile) -> Result<Vec<Declaration>, String> {
    let text = file
        .text
        .split("#[cfg(test)]")
        .next()
        .unwrap_or(file.text.as_str());
    let mut found = manifest_declarations(file, text)?;
    found.extend(native_declarations(file, text));
    found.extend(shared_library_declarations(file, text));
    Ok(found)
}

/// Return each artifact as the fact a rule reads.
pub(crate) fn facts(artifacts: &[Artifact]) -> Vec<serde_json::Value> {
    artifacts
        .iter()
        .map(|artifact| {
            serde_json::json!({
                "key": format!("interop:{}:{}", artifact.mechanism.label(), artifact.name),
                "span": {"path": artifact.declared_in},
                "language": artifact.language,
                "name": artifact.name,
                "mechanism": artifact.mechanism.label(),
                "declared_language": artifact.language,
                "references": artifact.referenced_by,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests;
