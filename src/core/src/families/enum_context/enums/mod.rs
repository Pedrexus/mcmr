use std::collections::BTreeMap;

/// The enumerations one file declares and their standard bases.
#[derive(Clone, Default)]
pub(in crate::families) struct Enums {
    pub(super) declared: BTreeMap<String, Vec<String>>,
}
