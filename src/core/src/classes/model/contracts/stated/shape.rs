/// Structural role one source module plays in its package.
pub(in crate::classes) struct ModuleShape {
    pub(in crate::classes) is_package: bool,
    pub(in crate::classes) is_reexport_only: bool,
    pub(in crate::classes) states_policy: bool,
}
