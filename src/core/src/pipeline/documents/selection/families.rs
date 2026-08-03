/// Typed fact families selected for one document extraction.
#[derive(Clone, Copy)]
pub(in crate::pipeline::documents) struct SelectedFamilies {
    pub(in crate::pipeline::documents) functions: bool,
    pub(in crate::pipeline::documents) calls: bool,
    pub(in crate::pipeline::documents) classes: bool,
    pub(in crate::pipeline::documents) import_bindings: bool,
    pub(in crate::pipeline::documents) syntax: bool,
    pub(in crate::pipeline::documents) attribute_accesses: bool,
    pub(in crate::pipeline::documents) string_expressions: bool,
}
