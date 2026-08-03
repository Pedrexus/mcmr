use std::collections::{BTreeMap, BTreeSet};

use super::contracts::{Declared, Identity, Stated};

/// Return the class one base name reaches, through this module's imports or its own body.
pub(in crate::classes) fn resolve(
    module: &Stated,
    base: &str,
    definitions: &BTreeMap<Identity, &Declared>,
    reexports: &BTreeMap<Identity, Identity>,
) -> Option<Identity> {
    let own = (module.module.clone(), base.to_string());
    if definitions.contains_key(&own) {
        return Some(own);
    }
    let imported = module
        .imported
        .iter()
        .find(|(_, name)| name == base)
        .cloned()?;
    defining_identity(imported, definitions, reexports)
}

fn defining_identity(
    held: Identity,
    definitions: &BTreeMap<Identity, &Declared>,
    reexports: &BTreeMap<Identity, Identity>,
) -> Option<Identity> {
    let mut visited = BTreeSet::new();
    let mut current = &held;
    let resolved = loop {
        if definitions.contains_key(current) {
            break current;
        }
        if !visited.insert(current) {
            return None;
        }
        current = reexports.get(current)?;
    };
    Some(resolved.clone())
}

/// Return every class some module reaching it ever calls, which is where one gets built.
pub(in crate::classes) fn built(
    stated: &[Stated],
    definitions: &BTreeMap<Identity, &Declared>,
) -> BTreeSet<Identity> {
    let mut found = BTreeSet::new();
    for module in stated {
        let reached = module.imported.iter().cloned().chain(
            module
                .declared
                .iter()
                .map(|class| (module.module.clone(), class.name.clone())),
        );
        for held in reached {
            if module.usage.called.contains(&held.1) && definitions.contains_key(&held) {
                found.insert(held);
            }
        }
    }
    found
}

/// Return which ordinary modules import which names from each module, keyed by the module read.
pub(in crate::classes) fn coimports(stated: &[Stated]) -> BTreeMap<&str, Vec<(&str, Vec<&str>)>> {
    let mut found: BTreeMap<&str, Vec<(&str, Vec<&str>)>> = BTreeMap::new();
    for module in stated.iter().filter(|module| !module.shape.is_package) {
        let mut taken: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for (origin, name) in &module.imported {
            taken
                .entry(origin.as_str())
                .or_default()
                .push(name.as_str());
        }
        for (origin, names) in taken {
            if origin != module.module {
                found
                    .entry(origin)
                    .or_default()
                    .push((module.module.as_str(), names));
            }
        }
    }
    found
}

/// Return which ordinary modules import each declared class, keyed by definition.
pub(in crate::classes) fn importers<'repository>(
    stated: &'repository [Stated],
    definitions: &BTreeMap<Identity, &Declared>,
) -> BTreeMap<Identity, BTreeSet<&'repository str>> {
    let mut found: BTreeMap<Identity, BTreeSet<&str>> = BTreeMap::new();
    for module in stated {
        if module.shape.is_package || module.shape.is_reexport_only {
            continue;
        }
        for held in &module.imported {
            if held.0 == module.module || !definitions.contains_key(held) {
                continue;
            }
            found
                .entry(held.clone())
                .or_default()
                .insert(module.module.as_str());
        }
    }
    found
}
