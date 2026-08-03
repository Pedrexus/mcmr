use oxc_ast::ast::Program;
use oxc_ast::ast_kind::AstKind;
use oxc_ast_visit::Visit;

pub(super) fn statement_count(program: &Program<'_>) -> usize {
    let mut counter = StatementCount::default();
    counter.visit_program(program);
    counter.count
}

#[derive(Default)]
struct StatementCount {
    count: usize,
}

impl<'ast> Visit<'ast> for StatementCount {
    fn enter_node(&mut self, kind: AstKind<'ast>) {
        if is_statement(&kind) {
            self.count += 1;
        }
    }
}

fn is_control(kind: &AstKind<'_>) -> bool {
    matches!(
        kind,
        AstKind::IfStatement(_)
            | AstKind::DoWhileStatement(_)
            | AstKind::WhileStatement(_)
            | AstKind::ForStatement(_)
            | AstKind::ForInStatement(_)
            | AstKind::ForOfStatement(_)
            | AstKind::WithStatement(_)
            | AstKind::SwitchStatement(_)
            | AstKind::TryStatement(_)
    )
}

fn is_declaration(kind: &AstKind<'_>) -> bool {
    matches!(
        kind,
        AstKind::VariableDeclaration(_)
            | AstKind::Function(_)
            | AstKind::Class(_)
            | AstKind::ImportDeclaration(_)
            | AstKind::ExportAllDeclaration(_)
            | AstKind::TSEnumDeclaration(_)
            | AstKind::TSTypeAliasDeclaration(_)
            | AstKind::TSInterfaceDeclaration(_)
            | AstKind::TSModuleDeclaration(_)
            | AstKind::TSImportEqualsDeclaration(_)
            | AstKind::TSExportAssignment(_)
            | AstKind::TSNamespaceExportDeclaration(_)
    )
}

fn is_simple(kind: &AstKind<'_>) -> bool {
    matches!(
        kind,
        AstKind::EmptyStatement(_)
            | AstKind::ExpressionStatement(_)
            | AstKind::ContinueStatement(_)
            | AstKind::BreakStatement(_)
            | AstKind::ReturnStatement(_)
            | AstKind::LabeledStatement(_)
            | AstKind::ThrowStatement(_)
            | AstKind::DebuggerStatement(_)
    )
}

fn is_statement(kind: &AstKind<'_>) -> bool {
    is_simple(kind) || is_control(kind) || is_declaration(kind)
}
