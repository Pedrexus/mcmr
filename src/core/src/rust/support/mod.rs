use crate::graph::Visibility;
use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use syn::{Item, Type};

/// Return one path as the `::` separated name the rest of the repository would write.
pub(super) fn path_name(path: &syn::Path) -> String {
    path.segments
        .iter()
        .map(|segment| segment.ident.to_string())
        .collect::<Vec<_>>()
        .join("::")
}

/// Return the outermost name one type states, looking through the references around it.
pub(super) fn rendered(declared: &Type) -> String {
    match declared {
        Type::Path(path) => path
            .path
            .segments
            .last()
            .map(|segment| segment.ident.to_string())
            .unwrap_or_default(),
        Type::Reference(inner) => rendered(&inner.elem),
        Type::Slice(inner) => rendered(&inner.elem),
        Type::Array(inner) => rendered(&inner.elem),
        Type::Paren(inner) => rendered(&inner.elem),
        Type::Group(inner) => rendered(&inner.elem),
        _ => String::new(),
    }
}

/// Return the source one span covers, which proc-macro2 gives as a line and column pair.
pub(super) fn spanned(source: &Source, at: Span) -> &str {
    let (start, end) = (at.start(), at.end());
    source.slice_location(start..end)
}

/// Return the name one expression reads, which is what a copy of it is a copy of.
pub(super) fn rendered_expression(expression: &syn::Expr) -> String {
    match expression {
        syn::Expr::Path(path) => path_name(&path.path),
        syn::Expr::Field(field) => match &field.member {
            syn::Member::Named(name) => {
                format!("{}.{name}", rendered_expression(&field.base))
            }
            syn::Member::Unnamed(index) => {
                format!("{}.{}", rendered_expression(&field.base), index.index)
            }
        },
        syn::Expr::MethodCall(call) => {
            format!("{}.{}()", rendered_expression(&call.receiver), call.method)
        }
        syn::Expr::Reference(inner) => rendered_expression(&inner.expr),
        syn::Expr::Paren(inner) => rendered_expression(&inner.expr),
        _ => String::new(),
    }
}

/// Return the span one piece of syntax covers, in the shape the Python models validate.
pub(super) fn source_span(source: &Source, span: Span) -> crate::protocol::Span {
    let (start, end) = (span.start(), span.end());
    crate::protocol::Span {
        path: source.relative.clone(),
        start_line: start.line,
        start_column: start.column,
        end_line: end.line,
        end_column: end.column,
    }
}

pub(super) fn locate(source: &Source, span: Span) -> Value {
    serde_json::to_value(source_span(source, span)).expect("a Rust source span must serialize")
}

pub(super) fn base(source: &Source, key: &str, span: Span) -> Value {
    json!({"key": key, "span": locate(source, span), "language": "rust"})
}

/// Return how widely one method of an `impl` block reaches.
///
/// A method satisfying a trait states no visibility of its own, because the trait already decided
/// one: wherever the trait is in scope the method is callable. Reading the missing keyword as
/// `private` would say a type implementing a public trait publishes nothing, which is the opposite
/// of what a trait implementation is for.
pub(super) fn member_reach(block: &syn::ItemImpl, declared: &syn::Visibility) -> Visibility {
    match block.trait_.is_some() {
        true => Visibility::Public,
        false => visibility(declared),
    }
}

/// Return how widely one declaration reaches, by the way Rust states it.
pub(super) fn visibility(declared: &syn::Visibility) -> Visibility {
    match declared {
        syn::Visibility::Public(_) => Visibility::Public,
        syn::Visibility::Restricted(restricted) => {
            if restricted.path.is_ident("crate") || restricted.path.is_ident("super") {
                Visibility::Internal
            } else {
                Visibility::Protected
            }
        }
        syn::Visibility::Inherited => Visibility::Private,
    }
}

pub(super) fn label(reach: Visibility) -> &'static str {
    match reach {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Internal => "internal",
        Visibility::Private => "private",
    }
}

/// Return the name one declared item states, whatever kind of item it is.
pub(super) fn declared_name(item: &Item) -> Option<String> {
    match item {
        Item::Struct(declared) => Some(declared.ident.to_string()),
        Item::Enum(declared) => Some(declared.ident.to_string()),
        Item::Union(declared) => Some(declared.ident.to_string()),
        Item::Trait(declared) => Some(declared.ident.to_string()),
        Item::Type(declared) => Some(declared.ident.to_string()),
        Item::Fn(declared) => Some(declared.sig.ident.to_string()),
        _ => None,
    }
}

pub(super) fn is_type(item: &Item) -> bool {
    matches!(
        item,
        Item::Struct(_) | Item::Enum(_) | Item::Union(_) | Item::Trait(_)
    )
}
