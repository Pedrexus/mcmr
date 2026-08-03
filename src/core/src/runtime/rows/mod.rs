use super::retention::LegacyRetention;

mod families;

pub(crate) use families::TypedFamilies;

/// Typed row destinations and their legacy compatibility needs.
#[derive(Default)]
pub(crate) struct TypedRows<'a> {
    pub(crate) families: TypedFamilies<'a>,
    pub(crate) retention: LegacyRetention,
}

impl TypedRows<'_> {
    pub(crate) fn contains(&self, family: &str) -> bool {
        match family {
            "FunctionFact" => self.families.functions.is_some(),
            "CallFact" => self.families.calls.is_some(),
            "ClassFact" => self.families.classes.is_some(),
            "ImportBindingFact" => self.families.import_bindings.is_some(),
            "SyntaxFact" => self.families.syntax.is_some(),
            "AttributeAccessFact" => self.families.attribute_accesses.is_some(),
            "StringExpressionFact" => self.families.string_expressions.is_some(),
            _ => false,
        }
    }

    pub(crate) fn fact_count(&self, legacy: &[String]) -> usize {
        typed_count(self.families.functions.as_deref(), "FunctionFact", legacy)
            + typed_count(self.families.calls.as_deref(), "CallFact", legacy)
            + typed_count(self.families.classes.as_deref(), "ClassFact", legacy)
            + typed_count(
                self.families.import_bindings.as_deref(),
                "ImportBindingFact",
                legacy,
            )
            + typed_count(self.families.syntax.as_deref(), "SyntaxFact", legacy)
            + typed_count(
                self.families.attribute_accesses.as_deref(),
                "AttributeAccessFact",
                legacy,
            )
            + typed_count(
                self.families.string_expressions.as_deref(),
                "StringExpressionFact",
                legacy,
            )
    }

    pub(crate) fn has_any(&self) -> bool {
        [
            "FunctionFact",
            "CallFact",
            "ClassFact",
            "ImportBindingFact",
            "SyntaxFact",
            "AttributeAccessFact",
            "StringExpressionFact",
        ]
        .into_iter()
        .any(|family| self.contains(family))
    }
}

fn typed_count<Record>(records: Option<&Vec<Record>>, family: &str, legacy: &[String]) -> usize {
    records
        .filter(|_| !legacy.iter().any(|selected| selected == family))
        .map_or(0, Vec::len)
}
