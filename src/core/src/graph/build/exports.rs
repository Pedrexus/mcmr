use crate::graph::{EdgeKind, Export, ExportBypass, Reference};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn enrich(
    exports: &mut [Export],
    references: &[Reference],
    export_references: &[Reference],
    modules: &BTreeSet<String>,
) {
    let consumers = consumers_by_export(exports, references, export_references);
    for (export, consumers) in exports.iter_mut().zip(consumers) {
        export.consumer_count = consumers.len();
    }
    let preferred = preferred_routes(exports);
    let imports = import_graph(references, modules);
    let reachability = reachable_modules(&imports, exports);
    let indexed = references_by_expression(references);
    for export in exports {
        export.bypasses = bypasses(
            export,
            indexed
                .get(export.target.as_str())
                .map_or(&[], Vec::as_slice),
            &preferred,
            &reachability,
        );
    }
}

fn consumers_by_export<'a>(
    exports: &[Export],
    references: &'a [Reference],
    export_references: &'a [Reference],
) -> Vec<BTreeSet<&'a str>> {
    let mut routes: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (index, export) in exports.iter().enumerate() {
        routes
            .entry(format!("{}.{}", export.module, export.name))
            .or_default()
            .push(index);
    }
    let mut consumers = vec![BTreeSet::new(); exports.len()];
    for reference in references.iter().chain(export_references) {
        for route in expression_routes(&reference.expression) {
            for index in routes.get(route).into_iter().flatten() {
                if outside_facade(&exports[*index], reference) {
                    consumers[*index].insert(reference.location.path.as_str());
                }
            }
        }
    }
    consumers
}

fn expression_routes(expression: &str) -> impl Iterator<Item = &str> {
    expression
        .match_indices('.')
        .map(|(index, _)| &expression[..index])
        .chain(std::iter::once(expression))
}

fn references_by_expression(references: &[Reference]) -> BTreeMap<&str, Vec<&Reference>> {
    let mut indexed: BTreeMap<&str, Vec<&Reference>> = BTreeMap::new();
    for reference in references {
        indexed
            .entry(reference.expression.as_str())
            .or_default()
            .push(reference);
    }
    indexed
}

fn outside_facade(export: &Export, reference: &Reference) -> bool {
    reference.location.path != export.path && !belongs_to(&reference.module, &export.module)
}

fn belongs_to(module: &str, package: &str) -> bool {
    module == package
        || module
            .strip_prefix(package)
            .is_some_and(|suffix| suffix.starts_with('.'))
}

fn preferred_routes(exports: &[Export]) -> BTreeMap<String, String> {
    let mut found = BTreeMap::new();
    for export in exports {
        let public_name = format!("{}.{}", export.module, export.name);
        let candidate = (public_name.split('.').count(), public_name);
        found
            .entry(export.target.clone())
            .and_modify(|current: &mut (usize, String)| {
                if candidate < *current {
                    *current = candidate.clone();
                }
            })
            .or_insert(candidate);
    }
    found
        .into_iter()
        .map(|(target, (_, route))| (target, route))
        .collect()
}

fn bypasses(
    export: &Export,
    references: &[&Reference],
    preferred: &BTreeMap<String, String>,
    reachability: &BTreeMap<String, BTreeSet<String>>,
) -> Vec<ExportBypass> {
    let public_name = format!("{}.{}", export.module, export.name);
    if preferred.get(&export.target) != Some(&public_name) {
        return Vec::new();
    }
    let defining_module = export
        .target
        .rsplit_once('.')
        .map_or(export.target.as_str(), |(module, _)| module);
    let defining_package = defining_module
        .rsplit_once('.')
        .map_or(defining_module, |(package, _)| package);
    references
        .iter()
        .filter(|reference| is_bypass(export, reference, &public_name, defining_package))
        .map(|reference| ExportBypass {
            path: reference.location.path.clone(),
            line: reference.location.line,
            expression: reference.expression.clone(),
            module_node: reference.location.module_node.clone(),
            replacement_module: replacement_module(reference, defining_module, &export.module),
            binding_count: reference.resolution.binding_count,
            is_cycle_safe: !reachability
                .get(&export.module)
                .is_some_and(|reachable| reachable.contains(&reference.module)),
        })
        .collect()
}

fn is_bypass(
    export: &Export,
    reference: &Reference,
    public_name: &str,
    defining_package: &str,
) -> bool {
    reference.kind == EdgeKind::Import
        && outside_facade(export, reference)
        && !nested_facade_implementation(export, reference)
        && !belongs_to(&reference.module, defining_package)
        && reference.expression != public_name
}

fn nested_facade_implementation(export: &Export, reference: &Reference) -> bool {
    let Some((distribution, _)) = export.module.split_once('.') else {
        return false;
    };
    let marker = format!("{distribution}/");
    export
        .path
        .find(&marker)
        .map(|offset| &export.path[..offset + marker.len()])
        .is_some_and(|root| reference.location.path.starts_with(root))
}

fn replacement_module(
    reference: &Reference,
    defining_module: &str,
    public_module: &str,
) -> Option<String> {
    reference.location.module_node.as_ref().and_then(|node| {
        if node.text == defining_module {
            return Some(public_module.to_string());
        }
        let owner = defining_module
            .strip_suffix(&node.text)
            .unwrap_or_default()
            .trim_end_matches('.');
        public_module
            .strip_prefix(owner)
            .map(|module| module.trim_start_matches('.').to_string())
    })
}

fn import_graph(
    references: &[Reference],
    modules: &BTreeSet<String>,
) -> BTreeMap<String, BTreeSet<String>> {
    let mut imports: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for reference in references
        .iter()
        .filter(|reference| reference.kind == EdgeKind::Import)
    {
        if let Some(target) = declaring_module(&reference.expression, modules) {
            imports
                .entry(reference.module.clone())
                .or_default()
                .insert(target.to_string());
        }
    }
    imports
}

fn declaring_module<'a>(expression: &'a str, modules: &BTreeSet<String>) -> Option<&'a str> {
    let mut candidate = expression;
    loop {
        if modules.contains(candidate) {
            return Some(candidate);
        }
        candidate = candidate.rsplit_once('.')?.0;
    }
}

fn reachable_modules(
    imports: &BTreeMap<String, BTreeSet<String>>,
    exports: &[Export],
) -> BTreeMap<String, BTreeSet<String>> {
    exports
        .iter()
        .map(|export| export.module.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|module| {
            let reachable = reachable_from(imports, &module);
            (module, reachable)
        })
        .collect()
}

fn reachable_from(imports: &BTreeMap<String, BTreeSet<String>>, start: &str) -> BTreeSet<String> {
    let mut reachable = BTreeSet::new();
    let mut pending = vec![start.to_string()];
    while let Some(module) = pending.pop() {
        if reachable.insert(module.clone())
            && let Some(dependencies) = imports.get(&module)
        {
            pending.extend(dependencies.iter().cloned());
        }
    }
    reachable
}
