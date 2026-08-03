use super::model::{Declared, Identity, Stated, built, coimports, importers, resolve};
use std::collections::{BTreeMap, BTreeSet};

mod analysis;
mod contracts;
mod index;
mod relations;
mod state;

pub(super) use contracts::{ClassAddress, SubclassReference};
use index::RepositoryIndex;
use relations::RepositoryRelations;

/// Every class this repository declares, joined to every module that reaches one.
///
/// The joins a class rule asks for are all one to many over the whole tree, so each one is indexed
/// once here rather than searched per class. A repository of ten thousand modules is what makes
/// that the difference between one pass and one that never finishes.
pub(super) struct Repository<'repository> {
    index: RepositoryIndex<'repository>,
    relations: RepositoryRelations<'repository>,
    states_policy: bool,
}

impl<'repository> Repository<'repository> {
    pub(super) fn of(stated: &'repository [Stated]) -> Self {
        let definitions: BTreeMap<Identity, &Declared> = stated
            .iter()
            .flat_map(|module| {
                module
                    .declared
                    .iter()
                    .map(|class| ((module.module.clone(), class.name.clone()), class))
            })
            .collect();
        let reexports: BTreeMap<Identity, Identity> = stated
            .iter()
            .filter(|module| module.shape.is_package)
            .flat_map(|module| {
                module
                    .imported
                    .iter()
                    .filter(|(_, name)| module.usage.exported.contains(name))
                    .map(|imported| {
                        (
                            (module.module.clone(), imported.1.clone()),
                            imported.clone(),
                        )
                    })
            })
            .collect();
        let mut bases: BTreeMap<Identity, Vec<Identity>> = BTreeMap::new();
        let mut subclasses: BTreeMap<Identity, Vec<Identity>> = BTreeMap::new();
        for module in stated {
            for class in &module.declared {
                let held = (module.module.clone(), class.name.clone());
                let resolved: Vec<Identity> = class
                    .bases
                    .iter()
                    .filter_map(|base| resolve(module, base, &definitions, &reexports))
                    .collect();
                for base in &resolved {
                    subclasses
                        .entry(base.clone())
                        .or_default()
                        .push(held.clone());
                }
                bases.insert(held, resolved);
            }
        }
        let mut repository = Self {
            index: RepositoryIndex {
                modules: stated
                    .iter()
                    .map(|module| (module.module.as_str(), module))
                    .collect(),
                paths: stated
                    .iter()
                    .map(|module| (module.module.as_str(), module.path.as_str()))
                    .collect(),
                owners: stated
                    .iter()
                    .map(|module| (module.path.as_str(), module.module.as_str()))
                    .collect(),
                importers: importers(stated, &definitions),
                definitions: definitions.clone(),
                bases,
                subclasses,
            },
            states_policy: stated.iter().any(|module| module.shape.states_policy),
            relations: RepositoryRelations {
                built: built(stated, &definitions),
                reexported: stated
                    .iter()
                    .filter(|module| module.shape.is_package)
                    .flat_map(|module| module.imported.iter().cloned())
                    .filter(|held| definitions.contains_key(held))
                    .collect(),
                reexported_names: stated
                    .iter()
                    .filter(|module| module.shape.is_package)
                    .flat_map(|module| module.usage.exported.iter().map(String::as_str))
                    .collect(),
                directly_exported: stated
                    .iter()
                    .flat_map(|module| {
                        module
                            .usage
                            .exported
                            .iter()
                            .map(|name| (module.module.clone(), name.clone()))
                    })
                    .filter(|held| definitions.contains_key(held))
                    .collect(),
                coimports: coimports(stated),
                model_packages: BTreeSet::new(),
                dispatched: BTreeSet::new(),
            },
        };
        repository.relations.dispatched = repository.dispatched_members();
        repository.relations.model_packages = repository.model_packages();
        repository
    }

    /// Return every path and member name that some class above or below also declares.
    fn dispatched_members(&self) -> BTreeSet<(&'repository str, &'repository str)> {
        let mut found = BTreeSet::new();
        for (held, class) in &self.index.definitions {
            let Some(path) = self.index.paths.get(held.0.as_str()) else {
                continue;
            };
            let related: BTreeSet<&str> = self
                .ancestors(held)
                .into_iter()
                .chain(self.descendants(held))
                .filter_map(|relative| self.index.definitions.get(&relative))
                .flat_map(|above| above.members.iter().map(|member| member.name.as_str()))
                .collect();
            for member in &class.members {
                if let Some(shared) = related.get(member.name.as_str()) {
                    found.insert((*path, *shared));
                }
            }
        }
        found
    }

    /// Return every directory named `models` that really holds the data models of this project.
    ///
    /// A folder of neural networks is also called `models`, and a placement rule that judged one
    /// as a shared data package would report every file it holds forever.
    fn model_packages(&self) -> BTreeSet<String> {
        self.index
            .definitions
            .iter()
            .filter(|(_, class)| class.shape.is_declarative)
            .filter_map(|(held, _)| self.index.paths.get(held.0.as_str()))
            .filter_map(|path| path.rsplit_once('/'))
            .filter(|(directory, _)| directory.rsplit('/').next() == Some("models"))
            .map(|(directory, _)| directory.to_string())
            .collect()
    }
}
