use super::scalar::ScalarKey;
use crate::bindings::generic_tables::schema::ScalarKind;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
pub(crate) struct ColumnCatalog {
    kinds: BTreeMap<String, BTreeSet<ScalarKind>>,
}

impl ColumnCatalog {
    pub(crate) fn columns(&self, reserved: &[&str]) -> Vec<(ScalarKey, String)> {
        self.kinds
            .iter()
            .flat_map(|(path, kinds)| {
                kinds.iter().map(move |kind| {
                    (
                        ScalarKey {
                            path: path.clone(),
                            kind: *kind,
                        },
                        column_name(path, *kind, kinds, reserved),
                    )
                })
            })
            .collect()
    }

    pub(crate) fn insert(&mut self, path: String, kind: ScalarKind) {
        self.kinds.entry(path).or_default().insert(kind);
    }
}

fn column_name(
    path: &str,
    kind: ScalarKind,
    kinds: &BTreeSet<ScalarKind>,
    reserved: &[&str],
) -> String {
    match (kinds.len() > 1, reserved.contains(&path)) {
        (true, true) => format!("field.{path}_{}", kind.suffix()),
        (true, false) => format!("{path}_{}", kind.suffix()),
        (false, true) => format!("field.{path}"),
        (false, false) => path.to_string(),
    }
}
