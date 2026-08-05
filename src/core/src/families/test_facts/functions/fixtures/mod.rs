use crate::walk::{qualified_name, walk};
use ruff_python_ast::{ModModule, Stmt};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn fixture_parameters(module: &ModModule) -> BTreeMap<String, Vec<String>> {
    walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item)
                if item.decorator_list.iter().any(|decorator| {
                    qualified_name(&decorator.expression).ends_with("fixture")
                }) =>
            {
                Some((
                    item.name.to_string(),
                    item.parameters
                        .iter()
                        .map(|parameter| parameter.name().to_string())
                        .collect(),
                ))
            }
            _ => None,
        })
        .collect()
}

pub(super) fn reached_fixtures(
    requested: &[String],
    fixtures: &BTreeMap<String, Vec<String>>,
) -> Vec<String> {
    let mut found = BTreeSet::new();
    let mut pending = requested.to_vec();
    while let Some(name) = pending.pop() {
        if !found.insert(name.clone()) {
            continue;
        }
        pending.extend(fixtures.get(&name).into_iter().flatten().cloned());
    }
    found.into_iter().collect()
}
