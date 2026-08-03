use std::collections::BTreeSet;

pub(crate) struct CaptureSelection {
    pub(crate) selected: BTreeSet<String>,
    pub(crate) mirrored: BTreeSet<String>,
}
