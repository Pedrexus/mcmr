use super::Uses;
use crate::families::collections::is_named;
use crate::walk::qualified_name;
use ruff_python_ast::Expr;

const READING_BUILTINS: &[&str] = &[
    "len",
    "iter",
    "reversed",
    "sorted",
    "enumerate",
    "sum",
    "min",
    "max",
    "any",
    "all",
    "next",
];

pub(super) fn recognize_call<'source>(
    uses: &mut Uses,
    item: &'source ruff_python_ast::ExprCall,
    name: &str,
) -> Vec<&'source Expr> {
    let mut remaining: Vec<&Expr> = item
        .arguments
        .args
        .iter()
        .chain(item.arguments.keywords.iter().map(|keyword| &keyword.value))
        .collect();
    let called = qualified_name(&item.func);
    if let Expr::Attribute(method) = item.func.as_ref()
        && is_named(&method.value, name)
    {
        uses.operations.insert(method.attr.to_string());
    } else if READING_BUILTINS.contains(&called.as_str())
        && item.arguments.args.iter().any(|held| is_named(held, name))
    {
        uses.operations.insert(called);
        remaining.retain(|held| !is_named(held, name));
    } else {
        remaining.push(item.func.as_ref());
    }
    remaining
}
