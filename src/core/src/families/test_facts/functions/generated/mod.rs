use crate::walk::qualified_name;
use ruff_python_ast::{Expr, ModModule, Stmt};
use std::collections::BTreeSet;

pub(super) fn generated_case_sources(module: &ModModule) -> BTreeSet<String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::Assign(item)
                if matches!(
                    item.value.as_ref(),
                    Expr::ListComp(_) | Expr::SetComp(_) | Expr::Generator(_)
                ) =>
            {
                item.targets.first()
            }
            Stmt::AnnAssign(item)
                if matches!(
                    item.value.as_deref(),
                    Some(Expr::ListComp(_) | Expr::SetComp(_) | Expr::Generator(_))
                ) =>
            {
                Some(item.target.as_ref())
            }
            _ => None,
        })
        .filter_map(|target| match target {
            Expr::Name(name) => Some(name.id.to_string()),
            _ => None,
        })
        .collect()
}

pub(super) fn generated_parametrization_count(
    item: &ruff_python_ast::StmtFunctionDef,
    generated: &BTreeSet<String>,
) -> usize {
    item.decorator_list
        .iter()
        .filter(|decorator| qualified_name(&decorator.expression).ends_with("parametrize"))
        .filter(|decorator| match &decorator.expression {
            Expr::Call(call) => matches!(
                call.arguments.args.get(1),
                Some(Expr::Name(name)) if generated.contains(name.id.as_str())
            ),
            _ => false,
        })
        .count()
}
