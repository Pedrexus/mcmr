use super::super::reference_index::ReferenceIndex;

/// What one module knows while its import bindings are built.
pub(super) struct ImportContext {
    pub(super) importer: String,
    pub(super) references: ReferenceIndex,
    pub(super) exported: Vec<String>,
}
