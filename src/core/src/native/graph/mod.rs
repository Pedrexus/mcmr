use super::parsing::parse;
use super::support::{
    bare, child, children, declares_pure_virtual, descendant, is_name, is_qualifier, is_type,
    native_parameter, trim_include, wrapped,
};
use crate::graph::{
    DatatypeKind, Edge, EdgeKind, Language, Node, NodeKind, Reference, Relation, Resolution,
    Stated, identity, node, parameter,
};
use crate::source::Source;
use std::collections::{BTreeMap, BTreeSet};
use tree_sitter::Node as Syntax;

mod collector;
mod header_path;
mod scope_entry;

use collector::Collector;
pub(super) use header_path::HeaderPath;
use scope_entry::ScopeEntry;

/// Build the part of the repository graph one C, C++, or CUDA file states.
pub fn graph(source: Source, module: &str, language: Language) -> Option<Stated> {
    let tree = parse(&source)?;
    let root = tree.root_node();
    let mut collector = Collector {
        owners: vec![identity(language, NodeKind::Module, module)],
        scopes: vec![module.to_string()],
        source,
        language,
        nodes: Vec::new(),
        edges: Vec::new(),
        references: Vec::new(),
    };
    collector.scoped(root);
    Some(Stated {
        nodes: collector.nodes,
        edges: collector.edges,
        references: collector.references,
        export_references: Vec::new(),
        aliases: BTreeMap::new(),
        exports: BTreeSet::new(),
        export_nodes: BTreeMap::new(),
    })
}

impl Collector {
    fn scope(&self) -> String {
        self.scopes
            .last()
            .cloned()
            .expect("the native collector must retain its module scope")
    }

    fn owner(&self) -> String {
        self.owners
            .last()
            .cloned()
            .expect("the native collector must retain its module owner")
    }

    /// Walk one scope, declaring what it holds and recording what its bodies reach.
    ///
    /// A namespace and a type both open a scope that qualifies every name inside it, a function
    /// owns every call its body makes, and anything else is walked through to whatever it holds.
    fn scoped(&mut self, node: Syntax) {
        for child in children(node) {
            match child.kind() {
                "preproc_include" => self.include(child),
                "namespace_definition" => self.namespace(child),
                "function_definition" => self.callable(child),
                "declaration" | "field_declaration" => self.declared(child),
                "call_expression" => {
                    self.call(child);
                    self.scoped(child);
                }
                _ if is_type(child) => self.datatype(child),
                _ => self.scoped(child),
            }
        }
    }

    fn include(&mut self, node: Syntax) {
        let Some(path) = node.child_by_field_name("path") else {
            return;
        };
        let written = trim_include(self.text(path)).to_string();
        // A quoted include is written from where the including file sits and a bracketed one is
        // written from wherever the toolchain looks, so only the first is walked against a path.
        let named = HeaderPath {
            including: match path.kind() {
                "string_literal" => &self.source.relative,
                _ => "",
            },
            written: &written,
        }
        .module();
        let owner = self.owner();
        self.push(
            Relation {
                source: &owner,
                target: &named,
                kind: EdgeKind::Import,
            },
            node,
        );
    }

    fn namespace(&mut self, node: Syntax) {
        let named = node
            .child_by_field_name("name")
            .map(|name| self.text(name).to_string())
            .unwrap_or_else(|| "anonymous".to_string());
        let qualname = format!("{}::{named}", self.scope());
        let mut declared = self.place(NodeKind::Module, &qualname, node);
        declared.is_package = true;
        let identifier = declared.id.clone();
        self.declare(declared, node);
        self.enter(ScopeEntry {
            qualname,
            owner: identifier,
        });
        if let Some(body) = node.child_by_field_name("body") {
            self.scoped(body);
        }
        self.leave();
    }

    fn datatype(&mut self, node: Syntax) {
        let Some(named) = child(node, "type_identifier").map(|name| self.text(name).to_string())
        else {
            return;
        };
        let qualname = format!("{}::{named}", self.scope());
        let kind = match node.kind() {
            "enum_specifier" => DatatypeKind::Enumeration,
            _ if declares_pure_virtual(node) => DatatypeKind::Contract,
            _ => DatatypeKind::Concrete,
        };
        let declared = self.place(NodeKind::Class, &qualname, node).datatype(kind);
        let identifier = declared.id.clone();
        self.declare(declared, node);
        if let Some(clause) = child(node, "base_class_clause") {
            for base in children(clause).into_iter().filter(|item| is_name(*item)) {
                let named = self.text(base).to_string();
                self.push(
                    Relation {
                        source: &identifier,
                        target: &named,
                        kind: EdgeKind::Inherit,
                    },
                    base,
                );
            }
        }
        self.enter(ScopeEntry {
            qualname,
            owner: identifier,
        });
        if let Some(body) = descendant(node, "field_declaration_list") {
            self.scoped(body);
        }
        self.leave();
    }

    fn callable(&mut self, node: Syntax) {
        let Some(declarator) = node.child_by_field_name("declarator") else {
            return;
        };
        let Some(named) = self.declarator_name(declarator) else {
            return;
        };
        let identifier = self.declare_callable(node, &named, declarator);
        self.owners.push(identifier);
        if let Some(body) = node.child_by_field_name("body") {
            self.scoped(body);
        }
        self.owners.pop();
    }

    /// Declare one callable and the signature and type references it owns.
    fn declare_callable(&mut self, node: Syntax, named: &str, declarator: Syntax) -> String {
        let qualname = self.qualify(named);
        let declared = self.place(self.member_or_free(named), &qualname, node);
        let identifier = declared.id.clone();
        self.declare(declared, node);
        self.signature(&identifier, declarator);
        self.named_type(&identifier, node);
        identifier
    }

    /// Record the parameters one signature takes and the types it names.
    ///
    /// None of these three dialects lets a caller name an argument, so every parameter binds by
    /// position. What they do state is a C++ default argument and a C++ parameter pack, and the
    /// grammar names both, so a signature says which of its positions a caller may leave out.
    fn signature(&mut self, owner: &str, declarator: Syntax) {
        let Some(list) = descendant(declarator, "parameter_list") else {
            return;
        };
        let held = owner.rsplit(':').next().unwrap_or_default().to_string();
        for (ordinal, (stated, kind, has_default)) in children(list)
            .into_iter()
            .filter_map(native_parameter)
            .enumerate()
        {
            self.named_type(owner, stated);
            let Some(named) = stated
                .child_by_field_name("declarator")
                .and_then(|inner| self.declarator_name(inner))
            else {
                continue;
            };
            let mut declared =
                parameter(self.language, &format!("{held}::{named}"), ordinal, kind);
            declared.has_default = has_default;
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(stated.start_position().row + 1);
            let identifier = declared.id.clone();
            self.nodes.push(declared);
            self.relate(
                Relation {
                    source: owner,
                    target: &identifier,
                    kind: EdgeKind::Define,
                },
                stated,
            );
        }
    }

    /// Record one declared member, which is a prototype, a field, or a variable.
    fn declared(&mut self, node: Syntax) {
        if let Some(declarator) = descendant(node, "function_declarator") {
            let Some(named) = self.declarator_name(declarator) else {
                return;
            };
            let qualname = self.qualify(&named);
            let kind = self.member_or_free(&named);
            let declared = self.place(kind, &qualname, node);
            let identifier = declared.id.clone();
            self.declare(declared, node);
            self.signature(&identifier, declarator);
            return;
        }
        let owner = self.owner();
        self.named_type(&owner, node);
        let Some(named) = node
            .child_by_field_name("declarator")
            .and_then(|inner| self.declarator_name(inner))
        else {
            return;
        };
        let kind = if self.owner().contains(":class:") {
            NodeKind::Attribute
        } else {
            NodeKind::Variable
        };
        let qualname = self.qualify(&named);
        let declared = self.place(kind, &qualname, node);
        self.declare(declared, node);
    }

    fn call(&mut self, node: Syntax) {
        let Some(function) = node.child_by_field_name("function") else {
            return;
        };
        let named = match function.kind() {
            "field_expression" => function
                .child_by_field_name("field")
                .map(|field| self.text(field).to_string())
                .unwrap_or_default(),
            _ => bare(self.text(function)),
        };
        let owner = self.owner();
        self.push(
            Relation {
                source: &owner,
                target: &named,
                kind: EdgeKind::Call,
            },
            node,
        );
    }

    /// Record the type one declaration names, and declare the type it states inline.
    ///
    /// A declaration either names a type that already exists somewhere, which is a dependency, or
    /// writes a whole enum or struct in the type position, which is a declaration that happens to
    /// sit where a name usually goes. Only the first is an edge, and the second is walked into so
    /// what it declares still reaches the graph.
    fn named_type(&mut self, owner: &str, node: Syntax) {
        let Some(stated) = node.child_by_field_name("type") else {
            return;
        };
        if is_type(stated) {
            self.datatype(stated);
            return;
        }
        let named = bare(self.text(stated));
        if is_qualifier(&named) {
            return;
        }
        self.push(
            Relation {
                source: owner,
                target: &named,
                kind: EdgeKind::Typed,
            },
            stated,
        );
    }

    fn member_or_free(&self, named: &str) -> NodeKind {
        if self.owner().contains(":class:") || named.contains("::") {
            NodeKind::Method
        } else {
            NodeKind::Function
        }
    }

    /// Return the repository-wide name one written name stands for inside the current scope.
    fn qualify(&self, written: &str) -> String {
        format!("{}::{written}", self.scope())
    }

    fn place(&self, kind: NodeKind, qualname: &str, at: Syntax) -> Node {
        let mut declared = node(self.language, kind, qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(at.start_position().row + 1);
        declared.source = matches!(
            kind,
            NodeKind::Method | NodeKind::Property | NodeKind::Attribute
        )
        .then(|| self.text(at).to_string());
        declared
    }

    fn enter(&mut self, entry: ScopeEntry) {
        self.scopes.push(entry.qualname);
        self.owners.push(entry.owner);
    }

    fn leave(&mut self) {
        self.owners.pop();
        self.scopes.pop();
    }

    fn text(&self, node: Syntax) -> &str {
        self.source
            .text
            .get(node.byte_range())
            .expect("a parser node range must fit its source")
            .trim()
    }

    fn declarator_name(&self, node: Syntax) -> Option<String> {
        if is_name(node) {
            return Some(self.text(node).to_string());
        }
        self.declarator_name(wrapped(node)?)
    }

    fn declare(&mut self, declared: Node, node: Syntax) {
        let owner = self.owner();
        let identifier = declared.id.clone();
        self.nodes.push(declared);
        self.relate(
            Relation {
                source: &owner,
                target: &identifier,
                kind: EdgeKind::Define,
            },
            node,
        );
    }

    fn relate(&mut self, relation: Relation<'_>, node: Syntax) {
        self.edges.push(Edge {
            source: relation.source.to_string(),
            target: relation.target.to_string(),
            kind: relation.kind,
            path: self.source.relative.clone(),
            line: node.start_position().row + 1,
            resolution: Resolution::Exact,
        });
    }

    fn push(&mut self, relation: Relation<'_>, node: Syntax) {
        if relation.target.is_empty() {
            return;
        }
        self.references.push(Reference {
            source: relation.source.to_string(),
            expression: relation.target.to_string(),
            language: self.language,
            module: self.scope(),
            resolution: crate::graph::ReferenceResolution {
                owner: None,
                receiver_type: None,
                binding_count: 0,
            },
            kind: relation.kind,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: node.start_position().row + 1,
                module_node: None,
            },
        });
    }
}

/// Return the module one included header names, read from where the including file sits.
///
/// A quoted include is written relative to the file that states it, so `../detail/algo.cuh` means
/// something different in every directory it appears in. Walking the path against the including
/// file is what turns all of those into the one module they all name.
impl HeaderPath<'_> {
    pub(super) fn module(self) -> String {
        let mut parts: Vec<&str> = self.including.split('/').collect();
        parts.pop();
        for step in self.written.split('/') {
            match step {
                "." | "" => {}
                ".." => {
                    if parts.last().is_some_and(|part| *part != "..") {
                        parts.pop();
                    } else {
                        parts.push("..");
                    }
                }
                name => parts.push(name),
            }
        }
        let joined = parts.join("/");
        joined
            .rsplit_once('.')
            .map(|(stem, _)| stem)
            .unwrap_or(&joined)
            .replace('/', "::")
    }
}
