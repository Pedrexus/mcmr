use crate::graph::{Attachment, EdgeKind, NodeKind, Reference, ResolutionContext, attach, stray};
use std::collections::BTreeMap;

/// Resolve one Rust reference against the repository, leaving what cannot be proved visible.
///
/// A path arrives already rewritten against the module that wrote it. Resolution then follows
/// local aliases and names visible from ancestor modules.
pub(crate) fn resolve(reference: &Reference, context: ResolutionContext<'_>) {
    let expanded = expanded(context.aliases, reference);
    let candidates = candidates(reference, &expanded);
    if attach(
        Attachment {
            reference,
            candidates: &candidates,
            symbols: context.symbols,
            relation_kind: reference.kind,
        },
        context.nodes,
        context.edges,
    ) {
        return;
    }
    let (kind, qualname) = unresolved(reference, expanded);
    stray(reference, kind, &qualname, context.nodes, context.edges);
}

fn candidates(reference: &Reference, expanded: &str) -> Vec<String> {
    match reference.kind {
        EdgeKind::Import => import_candidates(reference, expanded),
        _ => local_candidates(reference, expanded),
    }
}

fn import_candidates(reference: &Reference, expanded: &str) -> Vec<String> {
    std::iter::once(reference.expression.as_str())
        .chain((expanded != reference.expression).then_some(expanded))
        .flat_map(|expression| qualified_imports(reference, expression))
        .collect()
}

fn qualified_imports(reference: &Reference, expression: &str) -> Vec<String> {
    let crate_name = reference.module.split("::").next().unwrap_or_default();
    let head = expression.split("::").next().unwrap_or_default();
    let mut candidates = Vec::new();
    if head != crate_name && !matches!(head, "crate" | "self" | "super") {
        let mut scope: Vec<&str> = reference.module.split("::").collect();
        while !scope.is_empty() {
            let qualified = format!("{}::{expression}", scope.join("::"));
            let parts: Vec<&str> = qualified.split("::").collect();
            candidates.extend(
                (scope.len() + 1..=parts.len())
                    .rev()
                    .map(|size| parts[..size].join("::")),
            );
            scope.pop();
        }
    }
    let parts: Vec<&str> = expression.split("::").collect();
    candidates.extend((1..=parts.len()).rev().map(|size| parts[..size].join("::")));
    candidates
}

fn local_candidates(reference: &Reference, expanded: &str) -> Vec<String> {
    let mut candidates = vec![expanded.to_string(), reference.expression.clone()];
    if let Some(owner) = &reference.resolution.owner {
        candidates.push(format!("{owner}::{expanded}"));
    }
    let mut scope: Vec<&str> = reference.module.split("::").collect();
    while !scope.is_empty() {
        candidates.push(format!("{}::{expanded}", scope.join("::")));
        scope.pop();
    }
    candidates
}

fn unresolved(reference: &Reference, expanded: String) -> (NodeKind, String) {
    let head = expanded.split("::").next().unwrap_or(&expanded);
    match reference.kind {
        EdgeKind::Import if matches!(head, "self" | "super") => (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", reference.module, reference.expression),
        ),
        EdgeKind::Import => (NodeKind::ExternalModule, head.to_string()),
        _ if is_provided(head) => (NodeKind::ExternalSymbol, format!("core::{expanded}")),
        _ if expanded.contains("::") => (NodeKind::ExternalSymbol, expanded),
        _ => (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", reference.module, reference.expression),
        ),
    }
}

/// Return one written path with its leading name replaced by whatever a `use` bound it to.
///
/// The bindings that answer live in the nearest enclosing module that stated any, since a nested
/// module sees what its ancestors imported. Asking that question and rewriting the path are one
/// step for the caller, so they are one function here and no table is handed back to borrow.
fn expanded(
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    reference: &Reference,
) -> String {
    let expression = reference.expression.as_str();
    let (head, rest) = expression.split_once("::").unwrap_or((expression, ""));
    let mut scope: Vec<&str> = reference.module.split("::").collect();
    while !scope.is_empty() {
        if let Some(target) = aliases
            .get(&scope.join("::"))
            .and_then(|held| held.get(head))
        {
            return match rest.is_empty() {
                true => target.clone(),
                false => format!("{target}::{rest}"),
            };
        }
        scope.pop();
    }
    expression.to_string()
}

/// Whether one name is something the language itself provides rather than a crate.
fn is_provided(name: &str) -> bool {
    const NAMES: &[&str] = &[
        "bool",
        "char",
        "f32",
        "f64",
        "i8",
        "i16",
        "i32",
        "i64",
        "i128",
        "isize",
        "str",
        "u8",
        "u16",
        "u32",
        "u64",
        "u128",
        "usize",
        "String",
        "Vec",
        "Option",
        "Some",
        "None",
        "Result",
        "Ok",
        "Err",
        "Box",
        "Self",
        "self",
        "Iterator",
        "Default",
        "Clone",
        "Copy",
        "Debug",
        "PartialEq",
        "Eq",
        "PartialOrd",
        "Ord",
        "Hash",
        "From",
        "Into",
        "TryFrom",
        "TryInto",
        "AsRef",
        "Drop",
        "Fn",
        "FnMut",
        "FnOnce",
        "Send",
        "Sync",
        "Sized",
        "ToString",
    ];
    NAMES.contains(&name)
}
