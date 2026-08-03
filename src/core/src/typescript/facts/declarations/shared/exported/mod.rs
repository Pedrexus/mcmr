use oxc_ast::ast::{Declaration, Statement};

pub(super) fn exported_declaration<'a, 'ast>(
    statement: &'a Statement<'ast>,
) -> Option<&'a Declaration<'ast>> {
    let Statement::ExportNamedDeclaration(item) = statement else {
        return None;
    };
    item.declaration.as_ref()
}
