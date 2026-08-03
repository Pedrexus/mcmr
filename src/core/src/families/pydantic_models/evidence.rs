use std::collections::BTreeSet;

#[derive(Default)]
pub(super) struct ValidatorEvidence {
    pub(super) fields_read: BTreeSet<String>,
    pub(super) receiver_attributes: BTreeSet<String>,
    pub(super) has_self_call: bool,
    pub(super) declarative_constraint_count: usize,
}
