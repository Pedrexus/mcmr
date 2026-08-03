use crate::protocol::JsonObject;
use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use syn::spanned::Spanned;
use syn::visit::{self, Visit};
use syn::{Item, UseTree};

use super::support::{base, declared_name, is_type, spanned};

pub(super) fn module_fact(source: &Source, file: &syn::File) -> Value {
    let mut statements = StatementCount {
        count: file.items.len(),
    };
    statements.visit_file(file);
    JsonObject::new(base(
        source,
        &format!("module:{}", source.relative),
        Span::call_site(),
    ))
    .merged(json!({
        "physical_line_count": source.text.lines().count(),
        "statement_count": statements.count,
        "class_count": file.items.iter().filter(|item| is_type(item)).count(),
        "function_count": file
            .items
            .iter()
            .filter(|item| matches!(item, Item::Fn(_)))
            .count(),
        "is_package_initializer": source.relative.ends_with("/mod.rs")
            || source.relative.ends_with("/lib.rs"),
        "members": file
            .items
            .iter()
            .filter_map(|item| {
                declared_name(item).map(|name| json!({
                    "name": name,
                    "source": spanned(source, item.span()),
                }))
            })
            .collect::<Vec<_>>(),
    }))
}

struct StatementCount {
    count: usize,
}

impl Visit<'_> for StatementCount {
    fn visit_stmt(&mut self, statement: &syn::Stmt) {
        self.count += 1;
        visit::visit_stmt(self, statement);
    }
}

pub(super) fn import_facts(source: &Source, file: &syn::File) -> Vec<Value> {
    file.items
        .iter()
        .filter_map(|item| match item {
            Item::Use(declared) => Some(declared),
            _ => None,
        })
        .flat_map(|declared| {
            let public = matches!(declared.vis, syn::Visibility::Public(_));
            let span = declared.use_token.span;
            bindings(&declared.tree)
                .into_iter()
                .map(move |(bound, path)| (bound, path, public, span))
        })
        .map(|(bound, path, public, span)| {
            let references = source
                .text
                .matches(bound.as_str())
                .count()
                .checked_sub(1)
                .expect("an imported binding must occur in its own declaration");
            let root = path.split("::").next().unwrap_or(&path).to_string();
            let owned = matches!(root.as_str(), "crate" | "self" | "super");
            JsonObject::new(base(
                source,
                &format!("import:{}:{bound}", source.relative),
                span,
            ))
            .merged(json!({
                "name": bound,
                "module": path,
                "importer_module": source.relative.clone(),
                "reference_count": references,
                "has_qualifying_use": references > 0,
                "is_relative": root == "self" || root == "super",
                "is_project_owned": owned,
                "is_external": !owned,
                "is_reexported": public,
            }))
        })
        .collect()
}

/// Return every name one use tree binds, with the path each one was bound to.
///
/// A use tree nests groups and renames around the names it finally binds, so `use a::{b, c as d}`
/// binds two names to two different paths and neither of them is written where it is bound.
pub(super) fn bindings(tree: &UseTree) -> Vec<(String, String)> {
    fn walk(tree: &UseTree, prefix: &mut String, names: &mut Vec<(String, String)>) {
        match tree {
            UseTree::Path(path) => {
                let restore = prefix.len();
                if !prefix.is_empty() {
                    prefix.push_str("::");
                }
                prefix.push_str(&path.ident.to_string());
                walk(&path.tree, prefix, names);
                prefix.truncate(restore);
            }
            UseTree::Name(name) => names.push((name.ident.to_string(), prefix.clone())),
            UseTree::Rename(rename) => names.push((rename.rename.to_string(), prefix.clone())),
            UseTree::Glob(_) => names.push(("*".to_string(), prefix.clone())),
            UseTree::Group(group) => {
                for item in &group.items {
                    walk(item, prefix, names);
                }
            }
        }
    }
    let mut names = Vec::new();
    walk(tree, &mut String::new(), &mut names);
    names
}
