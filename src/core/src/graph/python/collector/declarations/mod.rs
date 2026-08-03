use super::{
    Collector, Owner, ReferenceRequest,
    support::{annotation_names, is_contract, python_parameters, python_visibility, tail},
};
use crate::graph::construction::{ExactEdge, identity, node, parameter, relate};
use crate::graph::contracts::{EdgeKind, Language, Node, NodeKind, ParameterKind};
use crate::walk::{annotation_name, qualified_name};
use ruff_python_ast::{
    AnyParameterRef, Decorator, Expr, Parameters, Stmt, StmtClassDef, StmtFunctionDef,
};
use ruff_text_size::Ranged;
use std::collections::BTreeMap;

mod assignment_target;
mod site;

use assignment_target::AssignmentTarget;
use site::DeclarationSite;

impl Collector {
    /// Record that one declaration names a type.
    pub(super) fn annotation(&mut self, source: &str, annotation: &Expr) {
        for name in annotation_names(annotation)
            .into_iter()
            .filter(|name| !name.is_empty())
        {
            self.reference(ReferenceRequest {
                source,
                expression: &name,
                kind: EdgeKind::Typed,
                offset: annotation.range().start(),
            });
        }
    }

    pub(super) fn assignment(
        &mut self,
        statement: &Stmt,
        target: &Expr,
        annotation: Option<String>,
    ) {
        let Some(target) = self.assignment_target(target) else {
            return;
        };
        let declared = self.assignment_node(statement, &target, annotation);
        self.store_assignment(declared, &target, statement);
    }

    pub(super) fn callable(&mut self, statement: &Stmt, item: &StmtFunctionDef) {
        let owner_kind = self.owners.last().unwrap().kind;
        let qualname = format!("{}.{}", self.owners.last().unwrap().qualname, item.name);
        let decorators = decorators(&item.decorator_list);
        let kind = Self::callable_kind(owner_kind, &decorators);
        let declared = self.callable_node(statement, item, kind, decorators);
        let declared_id = self.store_declaration(declared, statement);
        self.callable_signature(
            DeclarationSite {
                id: &declared_id,
                qualname: &qualname,
                statement,
            },
            item,
        );
        self.callable_body(
            Owner {
                id: declared_id,
                kind,
                qualname,
            },
            &item.body,
        );
    }

    pub(super) fn class(&mut self, statement: &Stmt, item: &StmtClassDef) {
        let qualname = format!("{}.{}", self.owners.last().unwrap().qualname, item.name);
        let declared = self.class_node(statement, item, &qualname);
        let declared_id = self.store_declaration(declared, statement);
        self.class_bases(&declared_id, item);
        self.class_body(
            Owner {
                id: declared_id,
                kind: NodeKind::Class,
                qualname,
            },
            &item.body,
        );
    }

    fn callable_kind(owner: NodeKind, decorators: &[String]) -> NodeKind {
        match owner {
            NodeKind::Class
                if decorators
                    .iter()
                    .any(|name| matches!(tail(name), "property" | "cached_property")) =>
            {
                NodeKind::Property
            }
            NodeKind::Class => NodeKind::Method,
            _ => NodeKind::Function,
        }
    }

    fn holder_kind(kind: NodeKind) -> NodeKind {
        if kind == NodeKind::Variable {
            NodeKind::Module
        } else {
            NodeKind::Class
        }
    }

    fn registered_component(item: &StmtClassDef) -> bool {
        item.arguments
            .iter()
            .flat_map(|arguments| arguments.args.iter())
            .map(qualified_name)
            .any(|base| matches!(tail(&base), "Component" | "Registry"))
    }

    fn assignment_node(
        &self,
        statement: &Stmt,
        target: &AssignmentTarget,
        annotation: Option<String>,
    ) -> Node {
        let mut declared = self.declaration_node(
            target.kind,
            &format!("{}.{}", target.holder, target.name),
            statement,
        );
        declared.source = (target.kind == NodeKind::Attribute)
            .then(|| self.source.slice(statement.range()).to_string());
        declared.visibility = python_visibility(&target.name);
        declared.annotation = annotation;
        declared
    }

    fn assignment_target(&self, target: &Expr) -> Option<AssignmentTarget> {
        match target {
            Expr::Name(item) => self.named_target(item),
            Expr::Attribute(item) => self.receiver_target(item),
            _ => None,
        }
    }

    fn callable_body(&mut self, owner: Owner, body: &[Stmt]) {
        self.owners.push(owner);
        self.types.push(BTreeMap::new());
        self.body(body);
        self.types.pop();
        self.owners.pop();
    }

    fn callable_node(
        &self,
        statement: &Stmt,
        item: &StmtFunctionDef,
        kind: NodeKind,
        decorators: Vec<String>,
    ) -> Node {
        let qualname = format!("{}.{}", self.owners.last().unwrap().qualname, item.name);
        let mut declared = self.declaration_node(kind, &qualname, statement);
        declared.source = (self.owners.last().unwrap().kind == NodeKind::Class)
            .then(|| self.source.slice(statement.range()).to_string());
        declared.visibility = python_visibility(item.name.as_str());
        self.callable_surface(&mut declared, item, decorators);
        declared
    }

    fn callable_signature(&mut self, site: DeclarationSite<'_>, item: &StmtFunctionDef) {
        if let Some(returns) = &item.returns {
            self.annotation(site.id, returns);
        }
        self.parameters(site, &item.parameters);
    }

    fn callable_surface(
        &self,
        declared: &mut Node,
        item: &StmtFunctionDef,
        mut decorators: Vec<String>,
    ) {
        if self.is_stub_surface() {
            decorators.push("external-binding".to_string());
        }
        declared.decorators = decorators;
        declared.asynchronous = item.is_async;
        declared.return_annotation = item
            .returns
            .as_ref()
            .map(|returns| annotation_name(returns));
    }

    fn class_bases(&mut self, declared: &str, item: &StmtClassDef) {
        for base in item
            .arguments
            .iter()
            .flat_map(|arguments| arguments.args.iter())
        {
            let expression = qualified_name(base);
            self.reference(ReferenceRequest {
                source: declared,
                expression: &expression,
                kind: EdgeKind::Inherit,
                offset: base.range().start(),
            });
        }
    }

    fn class_body(&mut self, owner: Owner, body: &[Stmt]) {
        self.classes.push(owner.id.clone());
        self.owners.push(owner);
        self.body(body);
        self.classes.pop();
        self.owners.pop();
    }

    fn class_node(&self, statement: &Stmt, item: &StmtClassDef, qualname: &str) -> Node {
        let mut declared = self.declaration_node(NodeKind::Class, qualname, statement);
        declared.visibility = python_visibility(item.name.as_str());
        declared.decorators = decorators(&item.decorator_list);
        if self.is_stub_surface() {
            declared.decorators.push("external-binding".to_string());
        }
        if Self::registered_component(item) {
            declared.decorators.push("registered-component".to_string());
        }
        declared.is_abstract = is_contract(item);
        declared
    }

    fn class_qualname(&self) -> String {
        self.classes
            .last()
            .unwrap()
            .rsplit(':')
            .next()
            .unwrap_or_default()
            .to_string()
    }

    fn declaration_node(&self, kind: NodeKind, qualname: &str, statement: &Stmt) -> Node {
        let mut declared = node(Language::Python, kind, qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.source.line_of(statement.range().start()));
        declared
    }

    fn is_receiver_attribute(&self, item: &ruff_python_ast::ExprAttribute) -> bool {
        matches!(item.value.as_ref(), Expr::Name(receiver)
            if matches!(receiver.id.as_str(), "self" | "cls"))
            && !self.classes.is_empty()
    }

    /// Whether the current declaration is part of a Python stub surface.
    fn is_stub_surface(&self) -> bool {
        self.source.relative.ends_with(".pyi")
            && self
                .owners
                .last()
                .is_some_and(|owner| owner.kind == NodeKind::Module)
    }

    fn named_target(&self, item: &ruff_python_ast::ExprName) -> Option<AssignmentTarget> {
        let owner = self.owners.last().unwrap();
        let kind = match owner.kind {
            NodeKind::Module => NodeKind::Variable,
            NodeKind::Class => NodeKind::Attribute,
            _ => return None,
        };
        Some(AssignmentTarget {
            kind,
            holder: owner.qualname.clone(),
            name: item.id.to_string(),
        })
    }

    fn parameter_node(
        &self,
        site: DeclarationSite<'_>,
        stated: AnyParameterRef<'_>,
        ordinal: usize,
        kind: ParameterKind,
    ) -> Node {
        let mut declared = parameter(
            Language::Python,
            &format!("{}.{}", site.qualname, stated.name()),
            ordinal,
            kind,
        );
        declared.has_default = stated.default().is_some();
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.source.line_of(site.statement.range().start()));
        declared.annotation = stated.annotation().map(annotation_name);
        declared
    }

    fn parameters(&mut self, site: DeclarationSite<'_>, parameters: &Parameters) {
        for (ordinal, (stated, kind)) in python_parameters(parameters).into_iter().enumerate() {
            let declared = self.parameter_node(site, stated, ordinal, kind);
            self.store_parameter(site, stated, declared);
        }
    }

    fn receiver_target(&self, item: &ruff_python_ast::ExprAttribute) -> Option<AssignmentTarget> {
        self.is_receiver_attribute(item).then(|| AssignmentTarget {
            kind: NodeKind::Attribute,
            holder: self.class_qualname(),
            name: item.attr.to_string(),
        })
    }

    fn store_assignment(&mut self, declared: Node, target: &AssignmentTarget, statement: &Stmt) {
        if self.graph.nodes.iter().any(|node| node.id == declared.id) {
            return;
        }
        let declared_id = declared.id.clone();
        self.graph.nodes.push(declared);
        let holder = identity(
            Language::Python,
            Self::holder_kind(target.kind),
            &target.holder,
        );
        relate(
            &mut self.graph.edges,
            ExactEdge {
                source: &holder,
                target: &declared_id,
                kind: EdgeKind::Define,
                path: &self.source.relative,
                line: self.source.line_of(statement.range().start()),
            },
        );
    }

    fn store_declaration(&mut self, declared: Node, statement: &Stmt) -> String {
        let declared_id = declared.id.clone();
        self.define(&declared_id, statement);
        self.graph.nodes.push(declared);
        declared_id
    }

    fn store_parameter(
        &mut self,
        site: DeclarationSite<'_>,
        stated: AnyParameterRef<'_>,
        declared: Node,
    ) {
        self.declare(stated.name().as_ref(), declared.annotation.clone());
        let declared_id = declared.id.clone();
        self.graph.nodes.push(declared);
        if let Some(declared_type) = stated.annotation() {
            self.annotation(site.id, declared_type);
        }
        relate(
            &mut self.graph.edges,
            ExactEdge {
                source: site.id,
                target: &declared_id,
                kind: EdgeKind::Define,
                path: &self.source.relative,
                line: self.source.line_of(site.statement.range().start()),
            },
        );
    }
}

fn decorators(items: &[Decorator]) -> Vec<String> {
    items
        .iter()
        .map(|decorator| qualified_name(&decorator.expression))
        .collect()
}
