use std::collections::{BTreeMap, BTreeSet};

mod action;
mod selection;

use action::CaptureAction;
pub(crate) use selection::CaptureSelection;

/// Keep schema-normalized families as serde values until the native Polars boundary consumes them.
///
/// A selected family can also have legacy row rules during the cutover. In that case the capture
/// clones the Rust value and leaves the original batch on the legacy stream. A fully table-native
/// family moves the value into this store and no serialized copy crosses PyO3.
#[derive(Default)]
pub(crate) struct GenericCapture {
    pub(crate) selected: BTreeSet<String>,
    pub(crate) mirrored: BTreeSet<String>,
    pub(crate) marked: BTreeSet<String>,
    pub(crate) rows: BTreeMap<String, Vec<serde_json::Value>>,
}

impl GenericCapture {
    pub(crate) fn new(selection: CaptureSelection) -> Self {
        Self {
            selected: selection.selected,
            mirrored: selection.mirrored,
            marked: BTreeSet::new(),
            rows: BTreeMap::new(),
        }
    }

    pub(super) fn accept(
        &mut self,
        family: &str,
        produced: &mut Vec<serde_json::Value>,
    ) -> CaptureAction {
        if !self.selected.contains(family) {
            return CaptureAction {
                captured: false,
                mirrored: false,
                newly_marked: false,
                row_count: produced.len(),
            };
        }
        let mirrored = self.mirrored.contains(family);
        let row_count = produced.len();
        if mirrored {
            self.rows
                .entry(family.to_string())
                .or_default()
                .extend(produced.iter().cloned());
        } else {
            self.rows
                .entry(family.to_string())
                .or_default()
                .append(produced);
        }
        CaptureAction {
            captured: true,
            mirrored,
            newly_marked: self.marked.insert(family.to_string()),
            row_count,
        }
    }

    pub(super) fn unseen(&self) -> Vec<String> {
        self.selected.difference(&self.marked).cloned().collect()
    }
}
