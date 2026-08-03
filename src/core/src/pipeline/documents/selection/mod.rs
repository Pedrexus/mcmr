use self::families::SelectedFamilies;
use crate::runtime::{LegacyRetention, TypedRows};

mod families;

/// Typed families one document extraction must retain.
#[derive(Clone, Copy)]
pub(super) struct ExtractionSelection {
    pub(in crate::pipeline::documents) families: SelectedFamilies,
    pub(in crate::pipeline::documents) retention: LegacyRetention,
}

impl ExtractionSelection {
    pub(super) fn of(typed: &TypedRows<'_>) -> Self {
        Self {
            families: SelectedFamilies {
                functions: typed.families.functions.is_some(),
                calls: typed.families.calls.is_some(),
                classes: typed.families.classes.is_some(),
                import_bindings: typed.families.import_bindings.is_some(),
                syntax: typed.families.syntax.is_some(),
                attribute_accesses: typed.families.attribute_accesses.is_some(),
                string_expressions: typed.families.string_expressions.is_some(),
            },
            retention: typed.retention,
        }
    }
}
