use crate::graph::Visibility;
use proc_macro2::Span;

pub(super) struct CallableDefinition<'a> {
    pub(super) attributes: &'a [syn::Attribute],
    pub(super) reach: Visibility,
    pub(super) span: Span,
}
