use super::exported::exported_declaration;
use oxc_ast::ast::{Class, Declaration, Statement};

/// Return the class one statement declares, whether or not it is exported.
pub(in crate::typescript::facts) fn declared_class<'a, 'ast>(
    statement: &'a Statement<'ast>,
) -> Option<&'a Class<'ast>> {
    match statement {
        Statement::ClassDeclaration(item) => Some(item),
        _ => match exported_declaration(statement)? {
            Declaration::ClassDeclaration(class) => Some(class),
            _ => None,
        },
    }
}
