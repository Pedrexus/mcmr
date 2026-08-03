use super::super::mapping::Mapping;
use super::options::CompilerOptions;
use crate::typescript::graph::paths::names::JoinedPath;
use crate::typescript::graph::paths::support::parent_of;
use serde::Deserialize;

#[derive(Debug, Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub(super) struct TypeScriptConfig {
    compiler_options: CompilerOptions,
    extends: Option<String>,
}

impl TypeScriptConfig {
    pub(super) fn mappings(&self, current: &str) -> Result<Vec<Mapping>, String> {
        self.compiler_options.mappings(parent_of(current))
    }

    pub(super) fn next_path(&self, current: &str) -> Result<Option<String>, String> {
        let Some(next) = self.normalized_extension(current) else {
            return Ok(None);
        };
        validated_extension(next).map(Some)
    }

    fn normalized_extension(&self, current: &str) -> Option<String> {
        let extends = self.extends.as_deref()?;
        extends.starts_with('.').then(|| {
            JoinedPath {
                parent: parent_of(current),
                child: extends,
            }
            .normalized()
        })
    }
}

fn validated_extension(mut next: String) -> Result<String, String> {
    if next == ".." || next.starts_with("../") {
        return Err(format!(
            "{next} leaves the repository in a TypeScript extends chain"
        ));
    }
    if !next.ends_with(".json") {
        next.push_str("/tsconfig.json");
    }
    Ok(next)
}
