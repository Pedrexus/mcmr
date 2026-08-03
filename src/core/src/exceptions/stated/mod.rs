use super::declared::Declared;

/// What one module states about declared exceptions and imported names.
pub(super) struct Stated {
    pub(super) module: String,
    pub(super) path: String,
    pub(super) is_package: bool,
    pub(super) is_reexport_only: bool,
    pub(super) declared: Vec<Declared>,
    pub(super) imported: Vec<(String, String)>,
}
