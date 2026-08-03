use super::{
    AccessRequest, Collector, ReferenceRequest,
    support::{dotted, normalize_quotes},
};
use crate::graph::construction::{ExactEdge, relate};
use crate::graph::contracts::{EdgeKind, Language, Reference};
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::Ranged;

impl Collector {
    pub(super) fn expression(&mut self, expression: &Expr) {
        match expression {
            Expr::Name(item) => self.name(item),
            Expr::Attribute(item) => self.attribute(expression, item),
            Expr::Call(item) => self.call(item),
            _ => self.children(expression),
        }
    }

    fn attribute(&mut self, expression: &Expr, item: &ruff_python_ast::ExprAttribute) {
        let Some(named) = dotted(expression)
            .filter(|name| !matches!(name.split('.').next(), Some("self" | "cls")))
        else {
            self.expression(&item.value);
            return;
        };
        let owner = self.owners.last().unwrap().id.clone();
        self.access(AccessRequest {
            source: &owner,
            expression: &named,
            offset: item.range().start(),
        });
    }

    fn call(&mut self, item: &ruff_python_ast::ExprCall) {
        let named = dotted(&item.func).unwrap_or_else(|| self.rendered(&item.func));
        let owner = self.owners.last().unwrap().id.clone();
        self.reference(ReferenceRequest {
            source: &owner,
            expression: &named,
            kind: EdgeKind::Call,
            offset: item.range().start(),
        });
        if dotted(&item.func).is_none() {
            self.expression(&item.func);
        }
        self.call_arguments(item);
    }

    fn call_arguments(&mut self, item: &ruff_python_ast::ExprCall) {
        for argument in &item.arguments.args {
            self.expression(argument);
        }
        for keyword in &item.arguments.keywords {
            self.expression(&keyword.value);
        }
    }

    fn children(&mut self, expression: &Expr) {
        for child in crate::walk::children(expression) {
            self.expression(child);
        }
    }

    fn name(&mut self, item: &ruff_python_ast::ExprName) {
        let owner = self.owners.last().unwrap().id.clone();
        self.access(AccessRequest {
            source: &owner,
            expression: item.id.as_str(),
            offset: item.range().start(),
        });
    }

    fn access(&mut self, request: AccessRequest<'_>) {
        self.reference(ReferenceRequest {
            source: request.source,
            expression: request.expression,
            kind: EdgeKind::Access,
            offset: request.offset,
        });
    }

    /// Return one expression as the single-line text an unresolved reference is named by.
    pub(super) fn rendered(&self, expression: &Expr) -> String {
        let text = self.source.slice(expression.range());
        let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
        normalize_quotes(&collapsed)
    }

    /// Return the type the receiver of one expression was declared with, if the scope said.
    pub(super) fn declared_type(&self, expression: &str) -> Option<String> {
        let receiver = expression.split('.').next()?;
        self.types
            .iter()
            .rev()
            .find_map(|scope| scope.get(receiver))
            .cloned()
    }

    /// Remember that one name in the current scope holds a value of one declared type.
    pub(super) fn declare(&mut self, name: &str, annotation: Option<String>) {
        if let Some(kind) = annotation.filter(|kind| !kind.is_empty())
            && let Some(scope) = self.types.last_mut()
        {
            scope.insert(name.to_string(), kind);
        }
    }

    pub(super) fn define(&mut self, target: &str, statement: &Stmt) {
        let owner = self.owners.last().unwrap().id.clone();
        relate(
            &mut self.graph.edges,
            ExactEdge {
                source: &owner,
                target,
                kind: EdgeKind::Define,
                path: &self.source.relative,
                line: self.source.line_of(statement.range().start()),
            },
        );
    }

    pub(super) fn reference(&mut self, request: ReferenceRequest<'_>) {
        self.graph.references.push(Reference {
            language: Language::Python,
            source: request.source.to_string(),
            expression: request.expression.to_string(),
            module: self.module.clone(),
            resolution: crate::graph::ReferenceResolution {
                owner: self
                    .classes
                    .last()
                    .map(|class| class.rsplit(':').next().unwrap_or_default().to_string()),
                receiver_type: self.declared_type(request.expression),
                binding_count: 0,
            },
            kind: request.kind,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: self.source.line_of(request.offset),
                module_node: None,
            },
        });
    }
}
