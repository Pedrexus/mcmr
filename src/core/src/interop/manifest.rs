use super::contracts::{Declaration, Mechanism};
use crate::lexical::CorpusFile;
use serde_json::Value;

pub(super) fn manifest_declarations(
    file: &CorpusFile,
    text: &str,
) -> Result<Vec<Declaration>, String> {
    let (names, language) = if file.path.ends_with("Cargo.toml") {
        (binaries(file, text)?, "rust")
    } else if file.path.ends_with("pyproject.toml") {
        (binaries(file, text)?, "python")
    } else if file.path.ends_with("package.json") {
        (node_binaries(file, text)?, "typescript")
    } else {
        return Ok(Vec::new());
    };
    Ok(names
        .into_iter()
        .map(|name| (name, Mechanism::Binary, language))
        .collect())
}

/// Return the binary names one TOML manifest declares, in `[[bin]]` or `[project.scripts]`.
pub(super) fn binaries(file: &CorpusFile, text: &str) -> Result<Vec<String>, String> {
    let parsed = text
        .parse::<toml::Table>()
        .map_err(|failure| format!("{} is not valid TOML: {failure}", file.path))?;
    let mut names = toml_binary_names(file, &parsed)?;
    names.extend(toml_script_names(file, &parsed)?);
    Ok(names)
}

fn toml_binary_names(file: &CorpusFile, parsed: &toml::Table) -> Result<Vec<String>, String> {
    let Some(declared) = parsed.get("bin") else {
        return Ok(Vec::new());
    };
    let entries = declared
        .as_array()
        .ok_or_else(|| format!("{} bin must be an array of tables", file.path))?;
    entries
        .iter()
        .map(|entry| {
            entry
                .as_table()
                .and_then(|table| table.get("name"))
                .and_then(toml::Value::as_str)
                .ok_or_else(|| format!("{} bin entry must state a text name", file.path))
        })
        .filter_map(|name| match name {
            Ok("") => None,
            Ok(name) => Some(Ok(name.to_string())),
            Err(failure) => Some(Err(failure)),
        })
        .collect()
}

fn toml_script_names(file: &CorpusFile, parsed: &toml::Table) -> Result<Vec<String>, String> {
    let Some(scripts) = parsed
        .get("project")
        .and_then(|project| project.get("scripts"))
    else {
        return Ok(Vec::new());
    };
    let table = scripts
        .as_table()
        .ok_or_else(|| format!("{} project.scripts must be a table", file.path))?;
    table
        .iter()
        .map(|(name, target)| {
            (!name.is_empty() && target.as_str().is_some())
                .then(|| name.clone())
                .ok_or_else(|| {
                    format!(
                        "{} project.scripts entries must have a name and text target",
                        file.path
                    )
                })
        })
        .collect()
}

pub(super) fn node_binaries(file: &CorpusFile, text: &str) -> Result<Vec<String>, String> {
    let parsed: Value = serde_json::from_str(text)
        .map_err(|failure| format!("{} is not valid JSON: {failure}", file.path))?;
    let names = match parsed.get("bin") {
        None => Vec::new(),
        Some(Value::Object(entries)) => {
            if entries
                .iter()
                .any(|(name, target)| name.is_empty() || !target.is_string())
            {
                return Err(format!(
                    "{} bin entries must have a name and text target",
                    file.path
                ));
            }
            entries.keys().cloned().collect()
        }
        Some(Value::String(_)) => {
            let name = parsed["name"]
                .as_str()
                .filter(|name| !name.is_empty())
                .ok_or_else(|| {
                    format!("{} with a string bin must state a text name", file.path)
                })?;
            vec![name.to_string()]
        }
        Some(_) => return Err(format!("{} bin must be a string or object", file.path)),
    };
    Ok(names.into_iter().filter(|name| !name.is_empty()).collect())
}
