use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use syn::spanned::Spanned;
use syn::{ImplItem, Item};

use super::support::{declared_name, is_type, locate, rendered, spanned};

mod expressions;
mod identity;
mod position;

use expressions::block_children;
pub(super) use expressions::expression_name;
use identity::DeclarationIdentity;

/// Every declaration this file states, each with its source and its tree.
///
/// The kinds are the shared vocabulary rather than Rust's own, so a rule written against a Python
/// declaration reads a Rust one without learning what an `ItemFn` is.
pub(super) fn syntax_facts(source: &Source, file: &syn::File) -> Vec<Value> {
    let mut facts = Vec::new();
    for item in &file.items {
        collect_item(source, item, &mut facts);
    }
    facts
}

fn collect_item(source: &Source, item: &Item, facts: &mut Vec<Value>) {
    match item {
        Item::Fn(declared) => collect_function(source, declared, facts),
        Item::Impl(block) => collect_methods(source, block, facts),
        _ => collect_type(source, item, facts),
    }
}

fn collect_function(source: &Source, declared: &syn::ItemFn, facts: &mut Vec<Value>) {
    let name = declared.sig.ident.to_string();
    facts.push(declaration(
        source,
        DeclarationIdentity {
            qualname: &name,
            kind: "callable",
        },
        declared.span(),
        || block_children(source, &declared.block),
    ));
}

fn collect_methods(source: &Source, block: &syn::ItemImpl, facts: &mut Vec<Value>) {
    let owner = rendered(&block.self_ty);
    for member in &block.items {
        if let ImplItem::Fn(method) = member {
            let name = format!("{owner}::{}", method.sig.ident);
            facts.push(declaration(
                source,
                DeclarationIdentity {
                    qualname: &name,
                    kind: "callable",
                },
                method.span(),
                || block_children(source, &method.block),
            ));
        }
    }
}

fn collect_type(source: &Source, item: &Item, facts: &mut Vec<Value>) {
    if let Some(name) = declared_name(item)
        && is_type(item)
    {
        facts.push(declaration(
            source,
            DeclarationIdentity {
                qualname: &name,
                kind: "type",
            },
            item.span(),
            Vec::new,
        ));
    }
}

fn declaration(
    source: &Source,
    identity: DeclarationIdentity<'_>,
    at: Span,
    children: impl Fn() -> Vec<Value>,
) -> Value {
    let tree = json!({
        "kind": crate::syntax::known(identity.kind),
        "name": identity.qualname.rsplit("::").next().unwrap_or(identity.qualname),
        "span": locate(source, at),
        "children": children(),
    });
    crate::syntax::fact(
        source,
        crate::syntax::SyntaxFactIdentity {
            language: "rust",
            qualname: identity.qualname,
            written: spanned(source, at),
        },
        tree,
    )
}
