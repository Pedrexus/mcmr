use crate::protocol::JsonObject;
use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use syn::spanned::Spanned;
use syn::{ImplItem, Item, Type};

use super::support::{
    base, label, locate, member_reach, path_name, rendered, spanned, visibility,
};

pub(super) fn class_fact(source: &Source, file: &syn::File) -> Value {
    let mut methods: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut traits: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (region, item) in file.items.iter().enumerate() {
        let Item::Impl(block) = item else { continue };
        let owner = rendered(&block.self_ty);
        if let Some((_, path, _)) = &block.trait_ {
            traits
                .entry(owner.clone())
                .or_default()
                .push(path_name(path));
        }
        for member in &block.items {
            let ImplItem::Fn(method) = member else {
                continue;
            };
            let receiver = method.sig.receiver().is_some();
            methods.entry(owner.clone()).or_default().push(json!({
                "name": method.sig.ident.to_string(),
                "span": locate(source, method.span()),
                "source": spanned(source, method.span()),
                "region": region,
                "kind": if receiver { "method" } else { "static_method" },
                "visibility": label(member_reach(block, &method.vis)),
            }));
        }
    }
    let classes: Vec<Value> = file
        .items
        .iter()
        .filter_map(|item| {
            let span = item.span();
            let (name, reach, fields) = match item {
                Item::Struct(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.fields.len(),
                ),
                Item::Enum(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.variants.len(),
                ),
                Item::Union(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.fields.named.len(),
                ),
                Item::Trait(declared) => {
                    (declared.ident.to_string(), visibility(&declared.vis), 0)
                }
                _ => return None,
            };
            Some(json!({
                "name": name.clone(),
                "path": source.relative.clone(),
                "span": locate(source, span),
                "source": spanned(source, span),
                "scope": "module",
                "visibility": label(reach),
                "direct_bases": traits.get(&name).cloned().unwrap_or_default(),
                "methods": methods.get(&name).cloned().unwrap_or_default(),
                "field_count": fields,
                "has_instance_fields": fields > 0,
            }))
        })
        .collect();
    JsonObject::new(base(
        source,
        &format!("classes:{}", source.relative),
        Span::call_site(),
    ))
    .merged(json!({"classes": classes}))
}

/// Return every name one type states, including the ones its generic arguments hold.
///
/// `BTreeMap<String, Node>` depends on three names rather than one, so a generic argument is
/// opened rather than read as part of a single type. A type is a dependency with no other trace:
/// nothing calls it, constructs it, or inherits it, so without this edge the types a signature
/// names look unreached by everything.
pub(super) fn type_names(declared: &Type) -> Vec<String> {
    match declared {
        Type::Path(path) => {
            let mut names = vec![path_name(&path.path)];
            for segment in &path.path.segments {
                let syn::PathArguments::AngleBracketed(arguments) = &segment.arguments else {
                    continue;
                };
                names.extend(arguments.args.iter().flat_map(|argument| match argument {
                    syn::GenericArgument::Type(inner) => type_names(inner),
                    _ => Vec::new(),
                }));
            }
            names
        }
        Type::Reference(inner) => type_names(&inner.elem),
        Type::Slice(inner) => type_names(&inner.elem),
        Type::Array(inner) => type_names(&inner.elem),
        Type::Paren(inner) => type_names(&inner.elem),
        Type::Group(inner) => type_names(&inner.elem),
        Type::Ptr(inner) => type_names(&inner.elem),
        Type::Tuple(tuple) => tuple.elems.iter().flat_map(type_names).collect(),
        Type::ImplTrait(item) => item.bounds.iter().flat_map(bound_names).collect(),
        Type::TraitObject(item) => item.bounds.iter().flat_map(bound_names).collect(),
        _ => Vec::new(),
    }
}

pub(super) fn bound_names(bound: &syn::TypeParamBound) -> Vec<String> {
    match bound {
        syn::TypeParamBound::Trait(item) => vec![path_name(&item.path)],
        _ => Vec::new(),
    }
}

/// Return every trait one set of attributes derives, which the compiler then implements.
pub(super) fn derives(attributes: &[syn::Attribute]) -> Vec<String> {
    let mut names = Vec::new();
    for attribute in attributes
        .iter()
        .filter(|attribute| attribute.path().is_ident("derive"))
    {
        attribute
            .parse_nested_meta(|derived| {
                names.push(path_name(&derived.path));
                Ok(())
            })
            .expect("a parsed derive attribute must expose valid nested metadata");
    }
    names
}

pub(super) fn external_attributes(attributes: &[syn::Attribute]) -> Vec<String> {
    attributes
        .iter()
        .map(|attribute| path_name(attribute.path()))
        .filter(|name| {
            matches!(
                name.rsplit("::").next(),
                Some(
                    "no_mangle"
                        | "proc_macro"
                        | "proc_macro_attribute"
                        | "proc_macro_derive"
                        | "pyclass"
                        | "pyfunction"
                        | "pymethods"
                )
            )
        })
        .collect()
}
