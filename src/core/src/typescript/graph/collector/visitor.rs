use super::contracts::{CallableDeclaration, CallableSignature, KeyedMember, MemberBody};
use super::imports::ImportedBinding;
use super::relations::WrittenReference;
use super::{Collector, Owner, key_name, member_reach};
use crate::graph::{DatatypeKind, EdgeKind, Language, NodeKind, Visibility, identity, node};
use crate::typescript::graph::paths::names::ImportedName;
use crate::typescript::graph::paths::{Located, WrittenSpecifier};
use crate::typescript::support::expression_name;
use oxc_ast::ast::{
    AccessorProperty, AssignmentExpression, AssignmentTarget, Class, ExportAllDeclaration,
    ExportDefaultDeclaration, ExportDefaultDeclarationKind, ExportNamedDeclaration,
    ExportSpecifier, Expression, Function, ImportDeclaration, MethodDefinition,
    PropertyDefinition, StaticMemberExpression, TSEnumDeclaration, TSInterfaceDeclaration,
    TSTypeAliasDeclaration, TSTypeParameter, TSTypeReference, VariableDeclarator,
};
use oxc_ast_visit::Visit;
use oxc_ast_visit::walk::{
    walk_class, walk_function, walk_method_definition, walk_ts_type_parameter,
    walk_variable_declarator,
};
use oxc_span::Span;
use oxc_syntax::scope::ScopeFlags;

impl Collector<'_> {
    fn within_owner(&mut self, owner: Owner, visit: impl FnOnce(&mut Self)) {
        self.enter(owner);
        visit(self);
        self.leave();
    }

    fn within_export(&mut self, visit: impl FnOnce(&mut Self)) {
        self.state.exporting = true;
        visit(self);
        self.state.exporting = false;
    }

    fn reexport(&mut self, item: &ExportNamedDeclaration<'_>) -> bool {
        let Some(from) = &item.source else {
            return false;
        };
        let located = self.specifiers.locate(WrittenSpecifier {
            from: &self.source.relative,
            value: &from.value,
        });
        let bindings = item
            .specifiers
            .iter()
            .map(ImportedBinding::from_export)
            .collect();
        self.reached(located, bindings, item.span);
        true
    }

    fn publish_alias(&mut self, specifier: &ExportSpecifier<'_>) {
        let published = specifier.exported.name().to_string();
        let local = specifier.local.name().to_string();
        self.state.names.exported.insert(local.clone());
        self.state.names.exported.insert(published.clone());
        if published == local {
            return;
        }
        let target = self
            .state
            .names
            .aliases
            .get(&local)
            .cloned()
            .unwrap_or_else(|| {
                ImportedName {
                    module: &self.module,
                    member: &local,
                }
                .render()
            });
        self.state.names.aliases.insert(published, target);
    }

    fn publish_named(&mut self, item: &ExportNamedDeclaration<'_>) {
        for specifier in &item.specifiers {
            self.publish_alias(specifier);
        }
        if let Some(declaration) = &item.declaration {
            self.within_export(|collector| collector.visit_declaration(declaration));
        }
    }

    fn remember_default(&mut self, named: Option<String>) {
        let Some(named) = named else {
            return;
        };
        self.state.names.aliases.insert(
            "default".to_string(),
            ImportedName {
                module: &self.module,
                member: &named,
            }
            .render(),
        );
        self.state.names.exported.insert(named);
    }

    fn declare_function(&mut self, named: &str, item: &Function<'_>) {
        let declared = CallableDeclaration::from_function(named, self.reach(), item.span, item);
        let owner = self.callable_owner(declared);
        self.signature(owner, CallableSignature::from_function(item));
    }

    fn method_owner(&mut self, named: &str, item: &MethodDefinition<'_>) -> Owner {
        if item.kind.is_constructor() {
            self.fields(item);
        }
        let visibility = member_reach(&item.key, item.accessibility);
        self.callable_owner(CallableDeclaration::from_method(named, visibility, item))
    }

    fn declare_method(&mut self, named: &str, item: &MethodDefinition<'_>) {
        let owner = self.method_owner(named, item);
        self.signature(owner, CallableSignature::from_method(item));
    }

    fn declare_variable(&mut self, named: &str, item: &VariableDeclarator<'_>) -> bool {
        if self.owner().kind != NodeKind::Module {
            return false;
        }
        let owner = self.variable_owner(named, item);
        self.within_owner(owner, |collector| {
            if let Some(value) = &item.init {
                collector.visit_expression(value);
            }
        });
        true
    }

    fn property_owner(&mut self, item: &PropertyDefinition<'_>) -> Option<Owner> {
        self.keyed_member(KeyedMember {
            key: &item.key,
            kind: NodeKind::Attribute,
            span: item.span,
            accessibility: item.accessibility,
            annotation: item.type_annotation.as_deref(),
        })
    }

    fn accessor_owner(&mut self, item: &AccessorProperty<'_>) -> Option<Owner> {
        self.keyed_member(KeyedMember {
            key: &item.key,
            kind: NodeKind::Property,
            span: item.span,
            accessibility: None,
            annotation: item.type_annotation.as_deref(),
        })
    }

    fn visit_member_value(&mut self, owner: Owner, body: MemberBody<'_, '_>) {
        self.within_owner(owner, |collector| {
            if let Some(annotation) = body.annotation {
                collector.visit_ts_type_annotation(annotation);
            }
            if let Some(value) = body.value {
                collector.visit_expression(value);
            }
        });
    }

    fn variable_owner(&mut self, named: &str, item: &VariableDeclarator<'_>) -> Owner {
        self.annotated_member(
            NodeKind::Variable,
            named,
            item.span,
            self.reach(),
            item.type_annotation.as_deref(),
        )
    }

    fn assigned_field(&mut self, item: &AssignmentExpression<'_>) {
        let AssignmentTarget::StaticMemberExpression(field) = &item.left else {
            return;
        };
        if !matches!(field.object, Expression::ThisExpression(_)) {
            return;
        }
        if let Some(holder) = self.state.classes.last().cloned() {
            self.store_assigned_field(holder, field, item.span);
        }
    }

    fn store_assigned_field(
        &mut self,
        holder: String,
        field: &StaticMemberExpression<'_>,
        span: Span,
    ) {
        let mut declared = node(
            Language::TypeScript,
            NodeKind::Attribute,
            &format!("{holder}.{}", field.property.name),
        );
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.line(span));
        let owner = Owner {
            id: identity(Language::TypeScript, NodeKind::Class, &holder),
            kind: NodeKind::Class,
            qualname: holder,
        };
        self.declare_for(declared, &owner, span);
    }

    fn reference_callee(&mut self, callee: &Expression<'_>, kind: EdgeKind, span: Span) {
        let owner = self.owner().id;
        if let Some(named) = expression_name(callee) {
            self.reference(WrittenReference {
                source: &owner,
                expression: &named,
                kind,
                span,
            });
        }
    }
}

fn default_export_name(item: &ExportDefaultDeclarationKind<'_>) -> Option<String> {
    match item {
        ExportDefaultDeclarationKind::FunctionDeclaration(held) => held
            .id
            .as_ref()
            .map(|identifier| identifier.name.to_string()),
        ExportDefaultDeclarationKind::ClassDeclaration(held) => held
            .id
            .as_ref()
            .map(|identifier| identifier.name.to_string()),
        ExportDefaultDeclarationKind::TSInterfaceDeclaration(held) => {
            Some(held.id.name.to_string())
        }
        ExportDefaultDeclarationKind::Identifier(held) => Some(held.name.to_string()),
        _ => None,
    }
}

/// Walk what one file declares and what its bodies reach.
impl<'ast> Visit<'ast> for Collector<'_> {
    fn visit_import_declaration(&mut self, item: &ImportDeclaration<'ast>) {
        let located = self.specifiers.locate(WrittenSpecifier {
            from: &self.source.relative,
            value: &item.source.value,
        });
        let bindings: Vec<ImportedBinding> = item
            .specifiers
            .iter()
            .flatten()
            .map(ImportedBinding::from_import)
            .collect();
        self.reached(located, bindings, item.span);
    }

    fn visit_export_named_declaration(&mut self, item: &ExportNamedDeclaration<'ast>) {
        if self.reexport(item) {
            return;
        }
        self.publish_named(item);
    }

    fn visit_export_default_declaration(&mut self, item: &ExportDefaultDeclaration<'ast>) {
        self.remember_default(default_export_name(&item.declaration));
        self.within_export(|collector| {
            collector.visit_export_default_declaration_kind(&item.declaration);
        });
    }

    fn visit_export_all_declaration(&mut self, item: &ExportAllDeclaration<'ast>) {
        let located = self.specifiers.locate(WrittenSpecifier {
            from: &self.source.relative,
            value: &item.source.value,
        });
        if let Located::Module(target) = &located {
            // A wholesale re-export names no symbol, so the module it reaches is remembered under
            // a key no identifier can spell and every unanswered lookup tries it.
            self.state
                .names
                .aliases
                .insert(format!("* {target}"), target.clone());
        }
        self.reached(located, Vec::new(), item.span);
    }

    fn visit_class(&mut self, item: &Class<'ast>) {
        let Some(named) = item.id.as_ref().map(|held| held.name.to_string()) else {
            walk_class(self, item);
            return;
        };
        self.class(&named, item);
    }

    fn visit_function(&mut self, item: &Function<'ast>, flags: ScopeFlags) {
        let Some(named) = item.id.as_ref().map(|held| held.name.to_string()) else {
            walk_function(self, item, flags);
            return;
        };
        self.declare_function(&named, item);
    }

    fn visit_method_definition(&mut self, item: &MethodDefinition<'ast>) {
        let Some(named) = key_name(&item.key) else {
            walk_method_definition(self, item);
            return;
        };
        self.declare_method(&named, item);
    }

    fn visit_property_definition(&mut self, item: &PropertyDefinition<'ast>) {
        let Some(owner) = self.property_owner(item) else {
            return;
        };
        self.visit_member_value(
            owner,
            MemberBody {
                annotation: item.type_annotation.as_deref(),
                value: item.value.as_ref(),
            },
        );
    }

    fn visit_accessor_property(&mut self, item: &AccessorProperty<'ast>) {
        let Some(owner) = self.accessor_owner(item) else {
            return;
        };
        self.visit_member_value(
            owner,
            MemberBody {
                annotation: None,
                value: item.value.as_ref(),
            },
        );
    }

    fn visit_ts_interface_declaration(&mut self, item: &TSInterfaceDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, DatatypeKind::Contract);
        for extended in &item.extends {
            if let Some(name) = expression_name(&extended.expression) {
                self.reference(WrittenReference {
                    source: &owner.id,
                    expression: &name,
                    kind: EdgeKind::Inherit,
                    span: extended.span,
                });
            }
        }
        self.signatures(owner, item.type_parameters.as_deref(), &item.body.body);
    }

    fn visit_ts_type_alias_declaration(&mut self, item: &TSTypeAliasDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, DatatypeKind::Contract);
        self.within_owner(owner, |collector| {
            if let Some(generics) = &item.type_parameters {
                collector.visit_ts_type_parameter_declaration(generics);
            }
            collector.visit_ts_type(&item.type_annotation);
        });
    }

    fn visit_ts_enum_declaration(&mut self, item: &TSEnumDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, DatatypeKind::Enumeration);
        self.enter(owner);
        for member in &item.body.members {
            let named = match &member.id {
                oxc_ast::ast::TSEnumMemberName::Identifier(held) => held.name.to_string(),
                oxc_ast::ast::TSEnumMemberName::String(held)
                | oxc_ast::ast::TSEnumMemberName::ComputedString(held) => held.value.to_string(),
                oxc_ast::ast::TSEnumMemberName::ComputedTemplateString(_) => continue,
            };
            let declared =
                self.place(NodeKind::Attribute, &named, member.span, Visibility::Public);
            self.declare(declared, member.span);
        }
        self.leave();
    }

    fn visit_variable_declarator(&mut self, item: &VariableDeclarator<'ast>) {
        let Some(named) = item.id.get_identifier_name() else {
            walk_variable_declarator(self, item);
            return;
        };
        if let Some(annotation) = &item.type_annotation {
            self.visit_ts_type_annotation(annotation);
        }
        if !self.bound_callable(&named, item) && !self.declare_variable(&named, item) {
            walk_variable_declarator(self, item);
        }
    }

    fn visit_call_expression(&mut self, item: &oxc_ast::ast::CallExpression<'ast>) {
        self.reference_callee(&item.callee, EdgeKind::Call, item.span);
        self.visit_expression(&item.callee);
        for argument in &item.arguments {
            self.visit_argument(argument);
        }
    }

    fn visit_new_expression(&mut self, item: &oxc_ast::ast::NewExpression<'ast>) {
        self.reference_callee(&item.callee, EdgeKind::Instantiate, item.span);
        for argument in &item.arguments {
            self.visit_argument(argument);
        }
    }

    fn visit_static_member_expression(
        &mut self,
        item: &oxc_ast::ast::StaticMemberExpression<'ast>,
    ) {
        let owner = self.owner().id;
        if let Some(named) = expression_name(&item.object) {
            let reached = format!("{named}.{}", item.property.name);
            self.reference(WrittenReference {
                source: &owner,
                expression: &reached,
                kind: EdgeKind::Access,
                span: item.span,
            });
        }
        self.visit_expression(&item.object);
    }

    fn visit_assignment_expression(&mut self, item: &AssignmentExpression<'ast>) {
        self.assigned_field(item);
        self.visit_assignment_target(&item.left);
        self.visit_expression(&item.right);
    }

    fn visit_ts_type_parameter(&mut self, item: &TSTypeParameter<'ast>) {
        self.state.names.generics.insert(item.name.name.to_string());
        walk_ts_type_parameter(self, item);
    }

    fn visit_ts_type_reference(&mut self, item: &TSTypeReference<'ast>) {
        let named = item.type_name.to_string();
        let head = named.split('.').next().unwrap_or_default();
        // A type parameter stands for whatever a caller supplies and `as const` names the value
        // rather than a type, so neither is a dependency on a declaration anything could reach.
        if !item.type_name.is_const() && !self.state.names.generics.contains(head) {
            let owner = self.owner().id;
            self.reference(WrittenReference {
                source: &owner,
                expression: &named,
                kind: EdgeKind::Typed,
                span: item.span,
            });
        }
        if let Some(arguments) = &item.type_arguments {
            self.visit_ts_type_parameter_instantiation(arguments);
        }
    }
}
