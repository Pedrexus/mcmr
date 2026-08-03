use super::exported::exported_declaration;
use oxc_ast::ast::{Declaration, Function, Statement};

/// Return the function one statement declares, whether or not it is exported.
pub(in crate::typescript::facts) fn declared_function<'a, 'ast>(
    statement: &'a Statement<'ast>,
) -> Option<&'a Function<'ast>> {
    match statement {
        Statement::FunctionDeclaration(item) => Some(item),
        _ => match exported_declaration(statement)? {
            Declaration::FunctionDeclaration(function) => Some(function),
            _ => None,
        },
    }
}
