use crate::graph::Visibility;
use oxc_ast::ast::{MethodDefinition, Statement};

mod class;
mod exported;
mod function;

pub(in crate::typescript::facts) use class::declared_class;
pub(in crate::typescript::facts) use function::declared_function;

pub(in crate::typescript::facts) fn declared_name(statement: &Statement) -> Option<String> {
    if let Some(class) = declared_class(statement) {
        return class.id.as_ref().map(|name| name.name.to_string());
    }
    declared_function(statement)
        .and_then(|function| function.id.as_ref().map(|name| name.name.to_string()))
}

/// Return the reach of one declaration from the module that states it.
pub(super) fn declaration_visibility(statement: &Statement) -> Visibility {
    if matches!(
        statement,
        Statement::ExportNamedDeclaration(_) | Statement::ExportDefaultDeclaration(_)
    ) {
        Visibility::Public
    } else {
        Visibility::Internal
    }
}

/// Return the name one class member states, including the private form that carries a hash.
pub(in crate::typescript::facts) fn member_name(method: &MethodDefinition) -> Option<String> {
    match &method.key {
        oxc_ast::ast::PropertyKey::PrivateIdentifier(item) => Some(item.name.to_string()),
        key => key.static_name().map(|name| name.to_string()),
    }
}

/// Return how widely one class member reaches, by the two ways this language states it.
pub(in crate::typescript::facts) fn member_visibility(method: &MethodDefinition) -> Visibility {
    if matches!(method.key, oxc_ast::ast::PropertyKey::PrivateIdentifier(_)) {
        return Visibility::Private;
    }
    match method.accessibility {
        Some(oxc_ast::ast::TSAccessibility::Private) => Visibility::Private,
        Some(oxc_ast::ast::TSAccessibility::Protected) => Visibility::Protected,
        _ => Visibility::Public,
    }
}
