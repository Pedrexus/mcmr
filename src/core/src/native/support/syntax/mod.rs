use crate::graph::ParameterKind;
use tree_sitter::Node as Syntax;

mod classification;

pub(crate) use classification::{is_name, is_type};

pub(crate) fn walk(root: Syntax<'_>) -> Vec<Syntax<'_>> {
    let mut found = Vec::new();
    let mut pending = vec![root];
    while let Some(node) = pending.pop() {
        found.push(node);
        let mut held = children(node);
        held.reverse();
        pending.extend(held);
    }
    found
}

pub(crate) fn statement_count(root: Syntax<'_>) -> usize {
    walk(root)
        .into_iter()
        .filter(|node| {
            node.kind().ends_with("_statement")
                || matches!(
                    node.kind(),
                    "declaration"
                        | "function_definition"
                        | "namespace_definition"
                        | "preproc_call"
                        | "preproc_def"
                        | "preproc_function_def"
                        | "preproc_include"
                )
        })
        .count()
}

pub(crate) fn children(node: Syntax<'_>) -> Vec<Syntax<'_>> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

pub(crate) fn executable_children(body: Syntax<'_>) -> Vec<Syntax<'_>> {
    children(body)
        .into_iter()
        .filter(|child| child.kind() != "comment")
        .collect()
}

pub(crate) fn child<'tree>(node: Syntax<'tree>, kind: &str) -> Option<Syntax<'tree>> {
    children(node).into_iter().find(|item| item.kind() == kind)
}

pub(crate) fn wrapped(node: Syntax<'_>) -> Option<Syntax<'_>> {
    match node.kind() {
        "reference_declarator" | "variadic_declarator" | "parenthesized_declarator" => {
            children(node).into_iter().next()
        }
        _ => node.child_by_field_name("declarator"),
    }
}

pub(crate) fn binding_level(node: Syntax<'_>) -> Syntax<'_> {
    let mut level = node;
    while let Some(held) = wrapped(level).filter(|held| !is_name(*held)) {
        level = held;
    }
    level
}

pub(crate) fn native_parameter(node: Syntax<'_>) -> Option<(Syntax<'_>, ParameterKind, bool)> {
    match node.kind() {
        "parameter_declaration" => Some((node, ParameterKind::PositionalOnly, false)),
        "optional_parameter_declaration" => Some((node, ParameterKind::PositionalOnly, true)),
        "variadic_parameter_declaration" => Some((node, ParameterKind::VarPositional, false)),
        _ => None,
    }
}

pub(crate) fn descendant<'tree>(node: Syntax<'tree>, kind: &str) -> Option<Syntax<'tree>> {
    let mut pending = std::collections::VecDeque::from(children(node));
    while let Some(item) = pending.pop_front() {
        if item.kind() == kind {
            return Some(item);
        }
        pending.extend(children(item));
    }
    None
}

pub(crate) fn enclosing_type(node: Syntax<'_>) -> Option<Syntax<'_>> {
    let mut walker = node.parent();
    while let Some(found) = walker {
        if is_type(found) {
            return Some(found);
        }
        walker = found.parent();
    }
    None
}

pub(crate) fn in_anonymous_namespace(node: Syntax) -> bool {
    let mut walker = node.parent();
    while let Some(found) = walker {
        if found.kind() == "namespace_definition" && found.child_by_field_name("name").is_none() {
            return true;
        }
        walker = found.parent();
    }
    false
}

/// Return every top-level declaration of one translation unit, looking through its namespaces.
pub(crate) fn declarations(root: Syntax<'_>) -> Vec<Syntax<'_>> {
    children(root)
        .into_iter()
        .flat_map(|node| match node.kind() {
            "namespace_definition" => node
                .child_by_field_name("body")
                .map(children)
                .unwrap_or_default(),
            _ => vec![node],
        })
        .collect()
}
