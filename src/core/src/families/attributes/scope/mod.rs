use super::super::enum_context::{Bindings, Enums};

/// Enumeration bindings in reach of one lexical scope.
pub(super) struct Scope {
    pub(super) bound: Bindings,
    pub(super) enums: Enums,
}
