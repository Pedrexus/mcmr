use super::Collector;
use crate::graph::{Edge, EdgeKind, Language, Node, Reference, Relation, Resolution};
use crate::rust::classes::type_names;
use crate::rust::graph::callable_identity::CallableIdentity;
use crate::rust::module::bindings;
use crate::rust::support::path_name;
use proc_macro2::Span;
use syn::spanned::Spanned;
use syn::visit::Visit;
use syn::{Item, Type};

impl Collector {
    /// Return the repository-wide name one written type name stands for.
    pub(super) fn qualify(&self, written: &str) -> String {
        match self.aliases.get(written) {
            Some(target) => target.clone(),
            None => format!("{}::{written}", self.scope()),
        }
    }

    pub(super) fn declare(&mut self, declared: Node, span: Span) {
        let owner = self.owner();
        let identifier = declared.id.clone();
        self.nodes.push(declared);
        self.relate(
            Relation {
                source: &owner,
                target: &identifier,
                kind: EdgeKind::Define,
            },
            span,
        );
    }

    pub(super) fn types(&mut self, owner: &str, declared: &Type, span: Span) {
        for name in type_names(declared) {
            self.reference(
                Relation {
                    source: owner,
                    target: &name,
                    kind: EdgeKind::Typed,
                },
                span,
            );
        }
    }

    /// Record every import one use declaration states, and what each binding now names.
    pub(super) fn import(&mut self, declared: &syn::ItemUse) {
        let owner = self.owner();
        for (bound, path) in bindings(&declared.tree) {
            self.import_binding(declared, &owner, bound, &path);
        }
    }

    fn import_binding(&mut self, declared: &syn::ItemUse, owner: &str, bound: String, path: &str) {
        let target = self.absolute(path);
        let reached = format!("{target}::{bound}");
        let is_glob = bound == "*";
        let expression = if is_glob { &target } else { &reached }.clone();
        self.references.push(Reference {
            source: owner.to_string(),
            // Give resolution the complete `use` path so it can stop at the deepest module
            // instead of the crate root that holds it.
            expression,
            language: Language::Rust,
            module: self.scope(),
            resolution: crate::graph::ReferenceResolution {
                owner: None,
                receiver_type: None,
                binding_count: 0,
            },
            kind: EdgeKind::Import,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: declared.use_token.span.start().line,
                module_node: None,
            },
        });
        // The import edge names the module it resolved to. A module that re-exports a symbol
        // reaches that symbol, and nothing else records it.
        if !is_glob {
            self.reference(
                Relation {
                    source: owner,
                    target: &reached,
                    kind: EdgeKind::Access,
                },
                declared.use_token.span,
            );
        }
        self.aliases
            .insert(bound, if is_glob { target } else { reached });
    }

    /// Return the repository-wide path one written path stands for.
    ///
    /// Rust writes a path from where it is read. `crate` is the crate root, `self` is this module,
    /// and each `super` climbs one. Rewriting all three against the module doing the reading is
    /// what lets one repository-wide table answer for every file in it.
    ///
    /// The module doing the reading is the innermost one that is open, not the file. A `mod tests`
    /// writing `use super::*` names the file around it, and climbing from the file instead would
    /// send every test module in the crate at the crate root.
    pub(in crate::rust) fn absolute(&self, written: &str) -> String {
        let reader = self
            .enclosing
            .last()
            .cloned()
            .expect("the Rust collector must retain its enclosing module");
        let mut segments = written.split("::");
        let head = segments.next().unwrap_or_default();
        let rest: Vec<&str> = segments.collect();
        let mut owner: Vec<&str> = reader.split("::").collect();
        let mut climbed = match head {
            "crate" => vec![
                *owner
                    .first()
                    .expect("a Rust module name must carry its crate"),
            ],
            "self" => owner,
            "super" => {
                if owner.len() == 1 {
                    return written.to_string();
                }
                owner.pop();
                owner
            }
            _ => return written.to_string(),
        };
        let mut remaining = rest.as_slice();
        while remaining.first() == Some(&"super") {
            if climbed.len() == 1 {
                return written.to_string();
            }
            climbed.pop();
            remaining = &remaining[1..];
        }
        climbed
            .into_iter()
            .chain(remaining.iter().copied())
            .collect::<Vec<_>>()
            .join("::")
    }

    pub(super) fn body(&mut self, identity: CallableIdentity<'_>, block: &syn::Block) {
        self.owners.push(identity.owner.to_string());
        self.scopes.push(identity.qualname.to_string());
        self.visit_block(block);
        self.scopes.pop();
        self.owners.pop();
    }

    /// Walk what a constant is set to, which is a table of real functions often enough to matter.
    pub(super) fn initializer(&mut self, owner: &str, value: &syn::Expr) {
        self.owners.push(owner.to_string());
        self.visit_expr(value);
        self.owners.pop();
    }

    pub(super) fn relate(&mut self, relation: Relation<'_>, span: Span) {
        self.edges.push(Edge {
            source: relation.source.to_string(),
            target: relation.target.to_string(),
            kind: relation.kind,
            path: self.source.relative.clone(),
            line: span.start().line,
            resolution: Resolution::Exact,
        });
    }

    pub(super) fn reference(&mut self, relation: Relation<'_>, span: Span) {
        if relation.target.is_empty() {
            return;
        }
        self.references.push(Reference {
            source: relation.source.to_string(),
            expression: self.absolute(relation.target),
            language: Language::Rust,
            module: self.scope(),
            resolution: crate::graph::ReferenceResolution {
                owner: self.receiver.clone(),
                receiver_type: None,
                binding_count: 0,
            },
            kind: relation.kind,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: span.start().line,
                module_node: None,
            },
        });
    }
}

/// Walk what a body does, which is where every call, construction, and member read is stated.
///
/// Only the expressions that name something outside themselves are recorded. A bare identifier is
/// almost always a local, so a path earns an edge once it carries a qualifier, which is exactly
/// when it names something another module declared.
impl Visit<'_> for Collector {
    fn visit_expr_call(&mut self, call: &syn::ExprCall) {
        match call.func.as_ref() {
            syn::Expr::Path(path) => {
                let owner = self.owner();
                let span = path
                    .path
                    .segments
                    .last()
                    .expect("a Rust call path must hold a segment")
                    .ident
                    .span();
                self.reference(
                    Relation {
                        source: &owner,
                        target: &path_name(&path.path),
                        kind: EdgeKind::Call,
                    },
                    span,
                );
            }
            other => self.visit_expr(other),
        }
        for argument in &call.args {
            self.visit_expr(argument);
        }
    }

    fn visit_expr_method_call(&mut self, call: &syn::ExprMethodCall) {
        let reached = match call.receiver.as_ref() {
            syn::Expr::Path(path) if path.path.is_ident("self") => self
                .receiver
                .clone()
                .map(|kind| format!("{kind}::{}", call.method)),
            _ => Some(call.method.to_string()),
        };
        if let Some(reached) = reached {
            let owner = self.owner();
            self.reference(
                Relation {
                    source: &owner,
                    target: &reached,
                    kind: EdgeKind::Call,
                },
                call.method.span(),
            );
        }
        self.visit_expr(&call.receiver);
        for argument in &call.args {
            self.visit_expr(argument);
        }
    }

    fn visit_expr_struct(&mut self, literal: &syn::ExprStruct) {
        let owner = self.owner();
        self.reference(
            Relation {
                source: &owner,
                target: &path_name(&literal.path),
                kind: EdgeKind::Call,
            },
            literal.brace_token.span.join(),
        );
        for field in &literal.fields {
            self.visit_expr(&field.expr);
        }
    }

    fn visit_expr_path(&mut self, read: &syn::ExprPath) {
        if read.path.segments.len() < 2 {
            return;
        }
        let owner = self.owner();
        let span = read
            .path
            .segments
            .last()
            .expect("a Rust expression path must hold a segment")
            .ident
            .span();
        self.reference(
            Relation {
                source: &owner,
                target: &path_name(&read.path),
                kind: EdgeKind::Access,
            },
            span,
        );
    }

    fn visit_type(&mut self, declared: &Type) {
        let owner = self.owner();
        self.types(&owner, declared, declared.span());
    }

    fn visit_item(&mut self, item: &Item) {
        self.item(item);
    }
}
