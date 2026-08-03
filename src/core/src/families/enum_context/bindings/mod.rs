use std::collections::BTreeMap;

/// The names one scope binds unambiguously to an enumeration value.
#[derive(Default)]
pub(in crate::families) struct Bindings {
    pub(super) names: BTreeMap<String, String>,
}
