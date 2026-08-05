use super::support::{
    child, declarations, dialect, is_name, is_type, statement_count, trim_include, walk, wrapped,
};
use crate::graph::Language;
use crate::protocol::JsonObject;
use crate::source::{Source, is_test_path};
use serde_json::{Value, json};
use tree_sitter::Node as Syntax;

mod calls;
mod declarations;
mod syntax;

/// One translation unit and everything the fact families read out of it.
pub(super) struct Unit {
    pub(super) source: Source,
    pub(super) language: Language,
}

impl Unit {
    pub(super) fn import_facts(&self, root: Syntax) -> Vec<Value> {
        walk(root)
            .into_iter()
            .filter(|node| node.kind() == "preproc_include")
            .filter_map(|node| {
                let path = node.child_by_field_name("path")?;
                let owned = path.kind() == "string_literal";
                let named = trim_include(self.text(path));
                let bound = named.rsplit('/').next().unwrap_or(named).to_string();
                let references = self
                    .source
                    .text
                    .matches(named)
                    .count()
                    .checked_sub(1)
                    .expect("an included path must occur in its own directive");
                Some(
                    JsonObject::new(
                        self.base(&format!("import:{}:{named}", self.source.relative), node),
                    )
                    .merged(json!({
                        "name": bound,
                        "module": named,
                        "importer_module": self.source.relative.clone(),
                        "reference_count": references,
                        "has_qualifying_use": true,
                        "is_relative": owned,
                        "is_project_owned": owned,
                        "is_external": !owned,
                    })),
                )
            })
            .collect()
    }

    pub(super) fn module_fact(&self, root: Syntax) -> Value {
        let declared = declarations(root);
        JsonObject::new(self.base(&format!("module:{}", self.source.relative), root)).merged(
            json!({
                "physical_line_count": self.source.text.lines().count(),
                "statement_count": statement_count(root),
                "class_count": declared.iter().filter(|node| is_type(**node)).count(),
                "function_count": declared
                    .iter()
                    .filter(|node| node.kind() == "function_definition")
                    .count(),
                "is_package_initializer": false,
                "is_test": is_test_path(&self.source.relative),
                "members": declared
                    .iter()
                    .filter_map(|node| {
                        self.declared_name(*node).map(|name| json!({
                            "name": name,
                            "source": self.text(*node),
                        }))
                    })
                    .collect::<Vec<_>>(),
            }),
        )
    }

    fn base(&self, key: &str, node: Syntax) -> Value {
        json!({
            "key": key,
            "span": self.locate(node),
            "language": dialect(self.language),
        })
    }

    /// Return the name one declarator finally binds, past every wrapper this language puts on it.
    ///
    /// A declaration here wraps its name in whatever it is being declared as, so a pointer to an
    /// array of functions buries the identifier several layers down and the only way to the name
    /// is to keep opening the wrapper.
    fn declarator_name(&self, node: Syntax) -> Option<String> {
        if is_name(node) {
            return Some(self.text(node).to_string());
        }
        self.declarator_name(wrapped(node)?)
    }

    /// Return the name one declaration states, whichever shape it states it in.
    fn declared_name(&self, node: Syntax) -> Option<String> {
        if is_type(node) {
            return child(node, "type_identifier").map(|name| self.text(name).to_string());
        }
        self.declarator_name(node.child_by_field_name("declarator")?)
    }

    fn locate(&self, node: Syntax) -> Value {
        let (start, end) = (node.start_position(), node.end_position());
        json!({
            "path": self.source.relative,
            "start_line": start.row + 1,
            "start_column": start.column,
            "end_line": end.row + 1,
            "end_column": end.column,
        })
    }

    fn text(&self, node: Syntax) -> &str {
        self.source
            .text
            .get(node.byte_range())
            .expect("a parser node range must fit its source")
            .trim()
    }
}
