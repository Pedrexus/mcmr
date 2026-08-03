use super::Uses;
use crate::families::collections::{comprehension_clauses, is_named};
use ruff_python_ast::Expr;

pub(super) fn recognize_comprehension<'source>(
    uses: &mut Uses,
    expression: &'source Expr,
    name: &str,
) -> Vec<&'source Expr> {
    let mut remaining: Vec<&Expr> = match expression {
        Expr::ListComp(item) => vec![item.elt.as_ref()],
        Expr::SetComp(item) => vec![item.elt.as_ref()],
        Expr::Generator(item) => vec![item.elt.as_ref()],
        Expr::DictComp(item) => item
            .key
            .iter()
            .map(AsRef::as_ref)
            .chain(std::iter::once(item.value.as_ref()))
            .collect(),
        _ => Vec::new(),
    };
    for generator in comprehension_clauses(expression) {
        if is_named(&generator.iter, name) {
            uses.operations.insert("iter".to_string());
        } else {
            remaining.push(&generator.iter);
        }
        remaining.extend(generator.ifs.iter());
    }
    remaining
}
