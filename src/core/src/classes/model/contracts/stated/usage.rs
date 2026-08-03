use std::collections::BTreeSet;

/// Names one module calls, reads, and exports.
pub(in crate::classes) struct ModuleUsage {
    pub(in crate::classes) called: BTreeSet<String>,
    pub(in crate::classes) read: BTreeSet<String>,
    pub(in crate::classes) exported: Vec<String>,
}
