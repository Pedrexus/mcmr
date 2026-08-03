use crate::graph::Visibility;
use proc_macro2::Span;

pub(super) struct FunctionDefinition<'a> {
    pub(super) declaration: Span,
    pub(super) reach: Visibility,
    pub(super) scope: &'a str,
    pub(super) body: Option<&'a syn::Block>,
}
