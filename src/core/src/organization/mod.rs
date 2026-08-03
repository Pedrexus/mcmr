use crate::discovery::{Document, Packages};
use crate::protocol::Span;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

use paths::{DirectoryPath, common_directory, directory_of, enum_package_parent};
use records::{Definition, Identity, Module, Reuse, ScopeKey};

mod paths;
mod records;

/// Repository-wide Python declarations whose best home depends on who imports them.
pub struct Organization {
    modules: Vec<Module>,
}

impl Organization {
    /// Parse each Python module once and retain only declarations and imports placement needs.
    pub fn of(documents: &[Document], packages: &Packages) -> Self {
        Self {
            modules: documents
                .iter()
                .filter(|document| document.relative.ends_with(".py"))
                .filter_map(|document| Module::of(document, packages))
                .collect(),
        }
    }

    /// State enum reuse scopes and the shape of files inside shared enum packages.
    pub fn enum_fact(&self) -> Value {
        let definitions = self.definitions(|module| &module.enums);
        let reused = self.reused(&definitions);
        let mut groups: BTreeMap<ScopeKey, Vec<Reuse>> = BTreeMap::new();
        for reuse in reused {
            groups
                .entry((
                    common_directory(
                        std::iter::once(reuse.definition.path.as_str())
                            .chain(reuse.importer_spans.iter().map(|span| span.path.as_str())),
                    ),
                    reuse.definition.is_test,
                ))
                .or_default()
                .push(reuse);
        }
        let assigned = assigned_definitions(&definitions, &groups);
        let scopes = groups
            .into_iter()
            .map(|((directory, is_test), held)| {
                let enum_count = assigned
                    .get(&(directory.clone(), is_test))
                    .map_or(0, Vec::len);
                let destination = directory.joined("enums.py");
                json!({
                    "destination": destination,
                    "enum_count": enum_count,
                    "reused_enum_count": held.len(),
                    "cross_module_import_count": held
                        .iter()
                        .map(|reuse| reuse.importer_spans.len())
                        .sum::<usize>(),
                })
            })
            .collect::<Vec<_>>();
        let files = self
            .modules
            .iter()
            .filter(|module| {
                directory_of(&module.location.path)
                    .split('/')
                    .any(|component| component == "enums")
            })
            .map(|module| {
                let importers = definitions
                    .iter()
                    .filter(|definition| definition.path == module.location.path)
                    .flat_map(|definition| self.importer_paths(definition))
                    .collect::<BTreeSet<_>>();
                let parent = enum_package_parent(&module.location.path);
                let branches = importers
                    .iter()
                    .filter_map(|path| parent.branch_below(path))
                    .collect::<BTreeSet<_>>();
                json!({
                    "path": module.location.path,
                    "top_level_class_count": module.top_level_class_count,
                    "enum_class_count": module.enums.len(),
                    "is_package_initializer": module.location.is_package,
                    "is_shared_across_unrelated_branches": branches.len() >= 2,
                })
            })
            .collect::<Vec<_>>();
        json!({
            "key": "enums:repository",
            "span": {"path": ""},
            "language": "python",
            "scopes": scopes,
            "files": files,
        })
    }

    /// State cohesive scopes that repeatedly import scattered typing declarations.
    pub fn typing_fact(&self) -> Value {
        let definitions = self.typing_definitions();
        let reused = self.reused(&definitions);
        let mut groups: BTreeMap<ScopeKey, Vec<Reuse>> = BTreeMap::new();
        for reuse in reused {
            groups
                .entry((
                    common_directory(
                        std::iter::once(reuse.definition.path.as_str())
                            .chain(reuse.importer_spans.iter().map(|span| span.path.as_str())),
                    ),
                    reuse.definition.is_test,
                ))
                .or_default()
                .push(reuse);
        }
        let assigned = assigned_definitions(&definitions, &groups);
        let scopes = groups
            .into_iter()
            .map(|((directory, is_test), held)| {
                let in_scope = assigned
                    .get(&(directory.clone(), is_test))
                    .cloned()
                    .unwrap_or_default();
                json!({
                    "path": directory,
                    "definitions": in_scope
                        .iter()
                        .map(|definition| json!({
                            "name": definition.identity.1,
                            "span": definition.span.as_ref().expect("a typing definition has a span"),
                        }))
                        .collect::<Vec<_>>(),
                    "reused_definitions": held
                        .iter()
                        .map(|reuse| json!({
                            "name": reuse.definition.identity.1,
                            "span": reuse.definition.span.as_ref().expect("a typing definition has a span"),
                            "importing_spans": reuse.importer_spans,
                        }))
                        .collect::<Vec<_>>(),
                })
            })
            .collect::<Vec<_>>();
        json!({
            "key": "typings:repository",
            "span": {"path": ""},
            "language": "python",
            "typing_scopes": scopes,
        })
    }

    fn definitions(&self, select: impl Fn(&Module) -> &Vec<String>) -> Vec<Definition> {
        self.modules
            .iter()
            .flat_map(|module| {
                select(module).iter().map(|name| Definition {
                    identity: (module.location.name.clone(), name.clone()),
                    path: module.location.path.clone(),
                    is_test: module.location.is_test,
                    span: None,
                })
            })
            .collect()
    }

    fn importer_paths(&self, definition: &Definition) -> Vec<String> {
        self.importer_spans(definition)
            .into_iter()
            .map(|span| span.path)
            .collect()
    }

    fn importer_spans(&self, definition: &Definition) -> Vec<Span> {
        self.modules
            .iter()
            .filter_map(|module| {
                (module.location.is_test == definition.is_test
                    && module.location.name != definition.identity.0)
                    .then(|| module.imports.get(&definition.identity).cloned())
                    .flatten()
            })
            .collect()
    }

    fn reused(&self, definitions: &[Definition]) -> Vec<Reuse> {
        definitions
            .iter()
            .filter_map(|definition| {
                let importer_spans = self.importer_spans(definition);
                (!importer_spans.is_empty()).then(|| Reuse {
                    definition: definition.clone(),
                    importer_spans,
                })
            })
            .collect()
    }

    fn typing_definitions(&self) -> Vec<Definition> {
        self.modules
            .iter()
            .flat_map(|module| {
                module.typings.iter().map(|definition| Definition {
                    identity: (module.location.name.clone(), definition.name.clone()),
                    path: module.location.path.clone(),
                    is_test: module.location.is_test,
                    span: Some(definition.span.clone()),
                })
            })
            .collect()
    }
}

/// Assign each declaration to exactly one candidate scope.
///
/// A reused declaration belongs to the common directory of its definition and importers, even
/// when a narrower candidate sits below it. A declaration nobody imports belongs to the deepest
/// candidate containing its file. This lets a scope count the local declarations that make a
/// shared module worthwhile without letting a parent count every child scope a second time.
fn assigned_definitions<'a>(
    definitions: &'a [Definition],
    groups: &BTreeMap<ScopeKey, Vec<Reuse>>,
) -> BTreeMap<ScopeKey, Vec<&'a Definition>> {
    let reused: BTreeMap<&Identity, &ScopeKey> = groups
        .iter()
        .flat_map(|(scope, held)| {
            held.iter()
                .map(move |reuse| (&reuse.definition.identity, scope))
        })
        .collect();
    let mut assigned: BTreeMap<ScopeKey, Vec<&Definition>> = BTreeMap::new();
    for definition in definitions {
        let scope = reused.get(&definition.identity).copied().or_else(|| {
            groups
                .iter()
                .filter(|((directory, is_test), _)| {
                    *is_test == definition.is_test && directory.holds(&definition.path)
                })
                .map(|(scope, _)| scope)
                .max_by_key(|(directory, _)| directory.len())
        });
        if let Some(scope) = scope {
            assigned.entry(scope.clone()).or_default().push(definition);
        }
    }
    assigned
}

#[cfg(test)]
mod tests;
