use crate::source::Source;
use crate::walk::{blocks, children, expressions};
use ruff_python_ast::{Expr, ModModule, Stmt};
use std::collections::BTreeMap;

mod placement;

use placement::Placement;

/// One place a module calls a name, and the class whose method body holds that call.
///
/// The owner is what separates a helper one class already behaves through from a helper the
/// module decomposes itself with, and it is empty for every call a class does not hold.
pub(super) struct CallSite {
    pub(super) node: crate::protocol::Node,
    pub(super) owner: String,
    pub(super) owner_definition: Option<crate::protocol::Node>,
}

/// Index every call site in one module by the bare name it calls.
///
/// A fix that inlines a helper has to name each place the helper is called, and inside one module
/// that is exactly the set of calls whose callee is its name. A caller in another module is a
/// different question, which the repository graph answers.
pub(super) fn call_sites(source: &Source, module: &ModModule) -> BTreeMap<String, Vec<CallSite>> {
    let mut sites: BTreeMap<String, Vec<CallSite>> = BTreeMap::new();
    let placement = Placement::root();
    index_calls(source, &module.body, &placement, &mut sites);
    sites
}

fn index_calls(
    source: &Source,
    body: &[Stmt],
    placement: &Placement,
    sites: &mut BTreeMap<String, Vec<CallSite>>,
) {
    for statement in body {
        for expression in expressions(statement) {
            index_call_expressions(source, expression, placement, sites);
        }
        match statement {
            Stmt::ClassDef(item) => {
                let child = Placement::inside_class(&item.name);
                index_calls(source, &item.body, &child, sites);
            }
            Stmt::FunctionDef(item) => {
                let child = placement
                    .clone()
                    .inside_callable(source.node_of("method", statement));
                index_calls(source, &item.body, &child, sites);
            }
            _ => {
                for block in blocks(statement) {
                    index_calls(source, block, placement, sites);
                }
            }
        }
    }
}

fn index_call_expressions(
    source: &Source,
    expression: &Expr,
    placement: &Placement,
    sites: &mut BTreeMap<String, Vec<CallSite>>,
) {
    if let Expr::Call(item) = expression
        && let Expr::Name(name) = item.func.as_ref()
    {
        sites
            .entry(name.id.to_string())
            .or_default()
            .push(CallSite {
                node: source.node_of("reference", item),
                owner: placement.owner().to_string(),
                owner_definition: placement.owner_definition(),
            });
    }
    for child in children(expression) {
        index_call_expressions(source, child, placement, sites);
    }
}
