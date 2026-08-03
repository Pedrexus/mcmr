use super::declarations::member_name;
use crate::source::Source;
use crate::typescript::support::range;
use contracts::{QualifiedName, SyntaxDeclaration};
use model::{SyntaxNode, SyntaxSemantic};
use oxc_ast::ast::{
    Class, ClassElement, Declaration, ExportDefaultDeclarationKind, Function, Program, Statement,
};
use serde_json::Value;

mod contracts;
mod model;
mod tree;

use tree::callable_initializer;

/// Return every declaration this module states with the language-neutral tree its rules read.
pub(super) fn syntax_facts(source: &Source, program: &Program) -> Vec<Value> {
    let mut facts = Vec::new();
    for statement in &program.body {
        syntax_statement(source, statement, &mut facts);
    }
    facts
}

fn class_methods(source: &Source, class: &Class<'_>) -> Vec<Value> {
    class
        .body
        .body
        .iter()
        .filter_map(|member| class_method(source, member))
        .collect()
}

fn class_method(source: &Source, member: &ClassElement<'_>) -> Option<Value> {
    let ClassElement::MethodDefinition(method) = member else {
        return None;
    };
    Some(
        SyntaxNode {
            children: Vec::new(),
            kind: SyntaxSemantic::Callable,
            name: member_name(method)?,
            span: method.span,
        }
        .value(source),
    )
}

fn class_tree(source: &Source, class: &Class<'_>, name: &str) -> Value {
    SyntaxNode {
        children: class_methods(source, class),
        kind: SyntaxSemantic::Type,
        name: name.to_string(),
        span: class.span,
    }
    .value(source)
}

fn method_facts(source: &Source, class: &Class<'_>, owner: &str) -> Vec<Value> {
    class
        .body
        .body
        .iter()
        .filter_map(|member| method_fact(source, member, owner))
        .collect()
}

fn method_fact(source: &Source, member: &ClassElement<'_>, owner: &str) -> Option<Value> {
    let ClassElement::MethodDefinition(method) = member else {
        return None;
    };
    let name = member_name(method)?;
    Some(
        SyntaxDeclaration {
            body: method.value.body.as_deref(),
            kind: SyntaxSemantic::Callable,
            name: QualifiedName { name: &name, owner },
            span: method.span,
        }
        .fact(source),
    )
}

fn syntax_class(source: &Source, class: &Class, facts: &mut Vec<Value>) {
    let Some(name) = class.id.as_ref().map(|item| item.name.to_string()) else {
        return;
    };
    facts.push(crate::syntax::fact(
        source,
        crate::syntax::SyntaxFactIdentity {
            language: "typescript",
            qualname: &name,
            written: source.slice(range(class.span)),
        },
        class_tree(source, class, &name),
    ));
    facts.extend(method_facts(source, class, &name));
}

fn syntax_declaration(source: &Source, declaration: &Declaration<'_>, facts: &mut Vec<Value>) {
    match declaration {
        Declaration::FunctionDeclaration(function) => syntax_function(source, function, "", facts),
        Declaration::ClassDeclaration(class) => syntax_class(source, class, facts),
        Declaration::VariableDeclaration(variables) => {
            syntax_variables(source, variables, "", facts)
        }
        _ => {}
    }
}

fn syntax_default(
    source: &Source,
    declaration: &ExportDefaultDeclarationKind<'_>,
    facts: &mut Vec<Value>,
) {
    match declaration {
        ExportDefaultDeclarationKind::FunctionDeclaration(function) => {
            syntax_function(source, function, "", facts);
        }
        ExportDefaultDeclarationKind::ClassDeclaration(class) => {
            syntax_class(source, class, facts)
        }
        _ => {}
    }
}

fn syntax_function(source: &Source, function: &Function, owner: &str, facts: &mut Vec<Value>) {
    let Some(name) = function.id.as_ref().map(|item| item.name.to_string()) else {
        return;
    };
    facts.push(
        SyntaxDeclaration {
            body: function.body.as_deref(),
            kind: SyntaxSemantic::Callable,
            name: QualifiedName { name: &name, owner },
            span: function.span,
        }
        .fact(source),
    );
}

fn syntax_statement(source: &Source, statement: &Statement, facts: &mut Vec<Value>) {
    match statement {
        Statement::ExportNamedDeclaration(item) => {
            if let Some(declaration) = &item.declaration {
                syntax_declaration(source, declaration, facts);
            }
        }
        Statement::ExportDefaultDeclaration(item) => {
            syntax_default(source, &item.declaration, facts)
        }
        _ => {
            if let Some(declaration) = statement.as_declaration() {
                syntax_declaration(source, declaration, facts);
            }
        }
    }
}

fn syntax_variables(
    source: &Source,
    declaration: &oxc_ast::ast::VariableDeclaration<'_>,
    owner: &str,
    facts: &mut Vec<Value>,
) {
    facts.extend(declaration.declarations.iter().filter_map(|variable| {
        let name = variable.id.get_identifier_name()?;
        let (span, body) = callable_initializer(variable)?;
        Some(
            SyntaxDeclaration {
                body,
                kind: SyntaxSemantic::Callable,
                name: QualifiedName { name: &name, owner },
                span,
            }
            .fact(source),
        )
    }));
}
