use super::contracts::{CallableDeclaration, CallableSignature, DeclaredParameter, KeyedMember};
use super::relations::WrittenReference;
use super::{Collector, Owner, key_name, member_reach, stated_reach};
use crate::graph::{DatatypeKind, EdgeKind, Language, Node, NodeKind, Visibility, parameter};
use crate::typescript::support::expression_name;
use oxc_ast::ast::{
    ArrowFunctionExpression, Class, Expression, FormalParameter, FormalParameters, Function,
    MethodDefinition, TSMethodSignature, TSPropertySignature, TSSignature, TSTypeAnnotation,
    TSTypeParameterDeclaration, VariableDeclarator,
};
use oxc_ast_visit::Visit;
use oxc_span::{GetSpan, Span};

impl<'ts> Collector<'ts> {
    /// Declare one class, interface, alias, or enum, and state whether it is a contract.
    pub(super) fn datatype(&mut self, named: &str, span: Span, kind: DatatypeKind) -> Owner {
        let declared = self
            .place(NodeKind::Class, named, span, self.reach())
            .datatype(kind);
        self.declare(declared, span)
    }

    /// Walk what one callable states after its own declaration: its signature and its body.
    pub(super) fn signature(&mut self, owner: Owner, signature: CallableSignature<'_, '_>) {
        self.enter(owner);
        if let Some(generics) = signature.generics {
            self.visit_ts_type_parameter_declaration(generics);
        }
        self.parameters(signature.parameters);
        if let Some(returns) = signature.returns {
            self.visit_ts_type_annotation(returns);
        }
        if let Some(body) = signature.body {
            self.visit_function_body(body);
        }
        self.leave();
    }

    /// Declare each positional or rest parameter while retaining destructured ordinals.
    pub(super) fn parameters(&mut self, params: &FormalParameters<'_>) {
        let owner = self.owner();
        let ordinary = params.items.iter().map(DeclaredParameter::ordinary);
        let rest = params.rest.iter().map(|held| DeclaredParameter::rest(held));
        for (ordinal, parameter) in ordinary.chain(rest).enumerate() {
            if let Some(annotation) = parameter.annotation {
                self.visit_ts_type_annotation(annotation);
            }
            if let Some(declared) = self.parameter_node(&owner, ordinal, &parameter) {
                self.store_parameter(&owner, declared, parameter.span);
            }
        }
    }

    fn parameter_node(
        &self,
        owner: &Owner,
        ordinal: usize,
        held: &DeclaredParameter<'_, '_>,
    ) -> Option<Node> {
        let named = held.name.as_deref()?;
        let mut declared = parameter(
            Language::TypeScript,
            &format!("{}.{named}", owner.qualname),
            ordinal,
            held.kind,
        );
        declared.has_default = held.optional;
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.line(held.span));
        declared.annotation = held
            .annotation
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        Some(declared)
    }

    fn store_parameter(&mut self, owner: &Owner, declared: Node, span: Span) {
        self.declare_for(declared, owner, span);
    }

    pub(super) fn annotated_member(
        &mut self,
        kind: NodeKind,
        named: &str,
        span: Span,
        visibility: Visibility,
        annotation: Option<&TSTypeAnnotation<'_>>,
    ) -> Owner {
        let mut declared = self.place(kind, named, span, visibility);
        declared.annotation = annotation.map(|held| self.rendered(held.type_annotation.span()));
        self.declare(declared, span)
    }

    pub(super) fn callable_owner(&mut self, callable: CallableDeclaration<'_, '_>) -> Owner {
        let mut declared = self.place(
            callable.kind,
            callable.name,
            callable.span,
            callable.visibility,
        );
        declared.asynchronous = callable.asynchronous;
        declared.return_annotation = callable
            .returns
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        self.declare(declared, callable.span)
    }

    pub(super) fn keyed_member(&mut self, member: KeyedMember<'_, '_>) -> Option<Owner> {
        let named = key_name(member.key)?;
        Some(self.annotated_member(
            member.kind,
            &named,
            member.span,
            member_reach(member.key, member.accessibility),
            member.annotation,
        ))
    }

    /// Declare the fields a constructor states in its own parameter list.
    ///
    /// A parameter carrying an access modifier or `readonly` declares a field of the class as well
    /// as a position of the constructor, and nothing else in the class body says so.
    pub(super) fn fields(&mut self, method: &MethodDefinition<'_>) {
        for held in &method.value.params.items {
            if held.accessibility.is_none() && !held.readonly {
                continue;
            }
            self.constructor_field(held);
        }
    }

    fn constructor_field(&mut self, field: &FormalParameter<'_>) {
        let Some(named) = field.pattern.get_identifier_name() else {
            return;
        };
        self.annotated_member(
            NodeKind::Attribute,
            &named,
            field.span,
            stated_reach(field.accessibility),
            field.type_annotation.as_deref(),
        );
    }

    /// Declare one member of an interface, which states a name without implementing it.
    pub(super) fn signatures(
        &mut self,
        owner: Owner,
        generics: Option<&TSTypeParameterDeclaration<'_>>,
        body: &[TSSignature<'_>],
    ) {
        self.enter(owner);
        if let Some(generics) = generics {
            self.visit_ts_type_parameter_declaration(generics);
        }
        for member in body {
            self.interface_member(member);
        }
        self.leave();
    }

    fn interface_member(&mut self, member: &TSSignature<'_>) {
        match member {
            TSSignature::TSPropertySignature(held) => self.interface_property(held),
            TSSignature::TSMethodSignature(held) => self.interface_method(held),
            _ => {}
        }
    }

    fn interface_property(&mut self, property: &TSPropertySignature<'_>) {
        let Some(named) = key_name(&property.key) else {
            return;
        };
        self.annotated_member(
            NodeKind::Attribute,
            &named,
            property.span,
            Visibility::Public,
            property.type_annotation.as_deref(),
        );
        if let Some(annotation) = &property.type_annotation {
            self.visit_ts_type_annotation(annotation);
        }
    }

    fn interface_method(&mut self, method: &TSMethodSignature<'_>) {
        let Some(named) = key_name(&method.key) else {
            return;
        };
        let member = self.callable_owner(CallableDeclaration::from_signature(&named, method));
        self.signature(member, CallableSignature::from_signature(method));
    }

    /// Declare one binding whose value is a callable, which is how most of this language writes one.
    pub(super) fn bound_callable(&mut self, named: &str, item: &VariableDeclarator<'_>) -> bool {
        match &item.init {
            Some(Expression::ArrowFunctionExpression(held)) => {
                self.arrow_callable(named, item, held);
                true
            }
            Some(Expression::FunctionExpression(held)) => {
                self.function_callable(named, item, held);
                true
            }
            Some(Expression::ClassExpression(held)) => {
                self.class(named, held);
                true
            }
            _ => false,
        }
    }

    fn arrow_callable(
        &mut self,
        named: &str,
        item: &VariableDeclarator<'_>,
        arrow: &ArrowFunctionExpression<'_>,
    ) {
        let declared = CallableDeclaration::from_arrow(named, self.reach(), item.span, arrow);
        let owner = self.callable_owner(declared);
        self.signature(owner, CallableSignature::from_arrow(arrow));
    }

    fn function_callable(
        &mut self,
        named: &str,
        item: &VariableDeclarator<'_>,
        function: &Function<'_>,
    ) {
        let declared =
            CallableDeclaration::from_function(named, self.reach(), item.span, function);
        let owner = self.callable_owner(declared);
        self.signature(owner, CallableSignature::from_function(function));
    }

    /// Declare one class, what it derives from, and what it promises to satisfy.
    pub(super) fn class(&mut self, named: &str, item: &Class<'_>) {
        let kind = match item.r#abstract {
            true => DatatypeKind::Contract,
            false => DatatypeKind::Concrete,
        };
        let owner = self.datatype(named, item.span, kind);
        self.class_relations(&owner, item);
        self.walk_class(owner, item);
    }

    fn class_relations(&mut self, owner: &Owner, item: &Class<'_>) {
        if let Some(base) = &item.super_class
            && let Some(name) = expression_name(base)
        {
            self.inherit(owner, name, base.span());
        }
        for implemented in &item.implements {
            self.inherit(owner, implemented.expression.to_string(), implemented.span);
        }
    }

    fn inherit(&mut self, owner: &Owner, expression: String, span: Span) {
        self.reference(WrittenReference {
            source: &owner.id,
            expression: &expression,
            kind: EdgeKind::Inherit,
            span,
        });
    }

    fn walk_class(&mut self, owner: Owner, item: &Class<'_>) {
        self.state.classes.push(owner.qualname.clone());
        self.enter(owner);
        if let Some(generics) = &item.type_parameters {
            self.visit_ts_type_parameter_declaration(generics);
        }
        self.visit_class_body(&item.body);
        self.leave();
        self.state.classes.pop();
    }
}
