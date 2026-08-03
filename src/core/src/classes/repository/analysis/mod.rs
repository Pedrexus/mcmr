use super::{ClassAddress, Repository, SubclassReference};
use crate::classes::model::{Declared, Identity, Member, camel_words, common_package, snake_case};
use crate::classes::records::CoupledTypeGroupRecord;
use crate::source::is_test_path;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

impl<'repository> Repository<'repository> {
    /// Return which repository class one file's record names, when the repository knows it.
    pub(super) fn identify(&self, address: ClassAddress<'_>) -> Option<Identity> {
        let held = (
            (*self.index.owners.get(address.path)?).to_string(),
            address.name.to_string(),
        );
        self.index.definitions.contains_key(&held).then_some(held)
    }

    /// Return every class above one class, nearest first, without visiting a cycle twice.
    pub(super) fn ancestors(&self, held: &Identity) -> Vec<Identity> {
        self.reachable(held, &self.index.bases)
    }

    /// Whether a resolved ancestor already establishes that this class is a declarative model.
    pub(super) fn inherits_declarative_model(&self, held: &Identity) -> bool {
        self.ancestors(held)
            .iter()
            .filter_map(|ancestor| self.index.definitions.get(ancestor))
            .any(|ancestor| ancestor.shape.is_declarative)
    }

    /// Whether a resolved ancestor already owns instance state for this class.
    pub(super) fn inherits_fields(&self, held: &Identity) -> bool {
        self.ancestors(held)
            .iter()
            .filter_map(|ancestor| self.index.definitions.get(ancestor))
            .any(|ancestor| ancestor.field_count > 0)
    }

    /// Return every class below one class, without visiting a cycle twice.
    pub(super) fn descendants(&self, held: &Identity) -> Vec<Identity> {
        self.reachable(held, &self.index.subclasses)
    }

    pub(super) fn reachable(
        &self,
        held: &Identity,
        links: &BTreeMap<Identity, Vec<Identity>>,
    ) -> Vec<Identity> {
        let mut found = Vec::new();
        let mut seen: BTreeSet<Identity> = BTreeSet::from([held.clone()]);
        let mut pending: Vec<Identity> = links.get(held).cloned().unwrap_or_default();
        while let Some(current) = pending.pop() {
            if !seen.insert(current.clone()) {
                continue;
            }
            pending.extend(links.get(&current).cloned().unwrap_or_default());
            found.push(current);
        }
        found
    }

    /// Whether any module reaching one class ever calls its name, which builds one.
    pub(super) fn is_built(&self, held: &Identity) -> bool {
        self.relations.built.contains(held)
    }

    /// Whether one class is offered outside the module declaring it, by name or by re-export.
    pub(super) fn is_exported(&self, held: &Identity, class: &Value) -> bool {
        class["is_exported"]
            .as_bool()
            .expect("ClassDeclaration.is_exported must be Boolean")
            || self.named_export(held)
    }

    /// Whether repository source explicitly exposes one class without consulting a fact record.
    pub(super) fn named_export(&self, held: &Identity) -> bool {
        self.relations.directly_exported.contains(held)
            || self.relations.reexported.contains(held)
            || self.relations.reexported_names.contains(held.1.as_str())
    }

    /// Whether the only place outside its own module that names one class is its one subclass.
    pub(super) fn only_reference_is_subclass(&self, reference: SubclassReference<'_>) -> bool {
        let [(child, _)] = reference.subclasses else {
            return false;
        };
        reference.importing == [child.as_str()]
            && self
                .index
                .modules
                .get(child.as_str())
                .is_some_and(|module| !module.usage.read.contains(&reference.held.1))
    }

    /// Whether the one base of one class is a base the closed world rule already owns.
    pub(super) fn base_is_removable(&self, held: &Identity) -> bool {
        let [only] = self
            .index
            .bases
            .get(held)
            .map(Vec::as_slice)
            .unwrap_or_default()
        else {
            return false;
        };
        let Some(base) = self.index.definitions.get(only) else {
            return false;
        };
        let subclasses = self.index.subclasses.get(only).cloned().unwrap_or_default();
        let importing: Vec<&str> = self
            .index
            .importers
            .get(only)
            .map(|found| found.iter().copied().collect())
            .unwrap_or_default();
        base.shape.is_plain
            && self.index.bases.get(only).is_none_or(Vec::is_empty)
            && subclasses.len() == 1
            && self.descendants(only).len() == 1
            && !self.is_built(only)
            && !self.named_export(only)
            && self.only_reference_is_subclass(SubclassReference {
                held: only,
                subclasses: &subclasses,
                importing: &importing,
            })
    }

    /// Whether one direct base of a class already inherits another direct base of the same class.
    pub(super) fn has_redundant_base(&self, held: &Identity) -> bool {
        let direct = self.index.bases.get(held).cloned().unwrap_or_default();
        direct.len() >= 2
            && direct.iter().any(|base| {
                self.ancestors(base)
                    .iter()
                    .any(|above| direct.contains(above))
            })
    }

    /// Whether two direct bases both supply the same member and at least one refuses to cooperate.
    pub(super) fn has_hazardous_collision(&self, held: &Identity) -> bool {
        let direct = self.index.bases.get(held).cloned().unwrap_or_default();
        if direct.len() < 2 {
            return false;
        }
        let supplied: Vec<Vec<&Member>> = direct.iter().map(|base| self.supplies(base)).collect();
        let names: BTreeSet<&str> = supplied
            .iter()
            .flatten()
            .map(|member| member.name.as_str())
            .collect();
        names.into_iter().any(|name| {
            let providers: Vec<&&Member> = supplied
                .iter()
                .filter_map(|held| held.iter().find(|member| member.name == name))
                .collect();
            providers.len() >= 2 && providers.iter().any(|member| !member.delegates_to_super)
        })
    }

    /// Return every concrete member one base hands down, its own first and its ancestors' after.
    pub(super) fn supplies(&self, base: &Identity) -> Vec<&'repository Member> {
        let mut found: Vec<&Member> = Vec::new();
        for held in std::iter::once(base.clone()).chain(self.ancestors(base)) {
            let Some(class) = self.index.definitions.get(&held) else {
                continue;
            };
            for member in &class.members {
                if member.is_concrete && !found.iter().any(|kept| kept.name == member.name) {
                    found.push(member);
                }
            }
        }
        found
    }

    /// Return the file a reused model belongs in, given every module that imports it.
    ///
    /// Consumers inside one package propose that package's own models module, and consumers
    /// spanning packages propose one file for the class below the nearest package they share.
    pub(super) fn proposed_destination(&self, held: &Identity, importing: &[&str]) -> String {
        let importing: Vec<&str> = importing
            .iter()
            .copied()
            .filter(|module| {
                self.index
                    .modules
                    .get(module)
                    .is_some_and(|stated| !is_test_path(&stated.path))
            })
            .collect();
        if importing.len() < 2 {
            return String::new();
        }
        let packages: Vec<&str> = importing
            .iter()
            .map(|module| {
                module
                    .rsplit_once('.')
                    .map(|(head, _)| head)
                    .unwrap_or(module)
            })
            .collect();
        let shared = common_package(&packages);
        let Some(directory) = self.directory(&shared) else {
            return String::new();
        };
        if packages.iter().all(|package| *package == shared) {
            return format!("{directory}models.py");
        }
        format!("{directory}models/{}.py", snake_case(&held.1))
    }

    /// Return where on disk one package sits, read off any module the package holds.
    pub(super) fn directory(&self, package: &str) -> Option<String> {
        self.index
            .paths
            .range(package..)
            .take_while(|(module, _)| module.starts_with(package))
            .find(|(module, _)| {
                module.len() == package.len() || module[package.len()..].starts_with('.')
            })
            .and_then(|(module, path)| {
                let depth = module[package.len()..].matches('.').count();
                let mut held: Vec<&str> = path.split('/').collect();
                let directory_depth = held.len().checked_sub(depth + 1)?;
                held.truncate(directory_depth);
                Some(held.iter().map(|part| format!("{part}/")).collect())
            })
    }

    /// Return the short co-imported role types one file declares under a shared name prefix.
    pub(super) fn coupled_groups(&self, path: &str) -> Vec<CoupledTypeGroupRecord> {
        let Some(module) = self.index.owners.get(path).copied() else {
            return Vec::new();
        };
        let Some(stated) = self.index.modules.get(module) else {
            return Vec::new();
        };
        let mut grouped: BTreeMap<String, Vec<&Declared>> = BTreeMap::new();
        for class in &stated.declared {
            let words = camel_words(&class.name);
            if words.len() >= 2 {
                grouped.entry(words[0].clone()).or_default().push(class);
            }
        }
        grouped
            .into_iter()
            .filter(|(_, held)| held.len() >= 2)
            .filter_map(|(_, held)| self.coupled_group(module, &held))
            .collect()
    }

    pub(super) fn coupled_group(
        &self,
        module: &str,
        held: &[&Declared],
    ) -> Option<CoupledTypeGroupRecord> {
        let words: Vec<Vec<String>> = held.iter().map(|class| camel_words(&class.name)).collect();
        let mut prefix = vec![words[0][0].clone()];
        while words.iter().all(|held| {
            held.len() > prefix.len() + 1 && held[prefix.len()] == words[0][prefix.len()]
        }) {
            prefix.push(words[0][prefix.len()].clone());
        }
        let shared = prefix.concat();
        let suffixes: Vec<String> = held
            .iter()
            .map(|class| class.name[shared.len()..].to_string())
            .collect();
        let names: Vec<&str> = held.iter().map(|class| class.name.as_str()).collect();
        let coimporting = self
            .relations
            .coimports
            .get(module)
            .map(Vec::as_slice)
            .unwrap_or_default()
            .iter()
            .filter(|(_, imported)| {
                imported.iter().filter(|name| names.contains(name)).count() >= 2
            })
            .count();
        Some(CoupledTypeGroupRecord {
            prefix: shared,
            span: held[0].span.clone(),
            role_suffixes: suffixes,
            type_count: held.len(),
            maximum_type_lines: held
                .iter()
                .map(|class| class.line_count)
                .max()
                .expect("a coupled class group must contain classes"),
            coimporting_module_count: coimporting,
        })
    }
}
