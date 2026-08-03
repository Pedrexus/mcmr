/// Legacy JSON families retained alongside their typed rows.
#[derive(Clone, Copy, Default)]
pub(crate) struct LegacyRetention {
    pub(crate) classes: bool,
    pub(crate) import_bindings: bool,
    pub(crate) syntax: bool,
}
