use crate::source::Source;
use crate::walk::{annotation_name, blocks, children, expressions, qualified_name};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

/// Every name one file binds, with the scope that binds it and the typing declarations it states.
///
/// Where a name is bound is what decides who can reach it, so a module constant, a class attribute
/// and a local all arrive named by their scope rather than folded together. Only a module-scope
/// name carries its references, since it is the only one this file can claim to have found every
/// use of, and finding them is a scan of the whole module per name.
pub fn symbols(source: &Source, module: &ModModule) -> Value {
    let assignments: Vec<Value> = scoped_assignments(module)
        .into_iter()
        .map(|(scope, name, range)| {
            json!({
                "name": name.clone(),
                "scope": scope,
                "is_constant_assignment": name.chars().all(|letter| !letter.is_lowercase()),
                "returns_boolean": false,
                "reference": (scope == "module")
                    .then(|| bound(source, module, &name, range)),
            })
        })
        .collect();
    let predicates: Vec<Value> = module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item)
                if item.decorator_list.is_empty()
                    && item
                        .returns
                        .as_ref()
                        .is_some_and(|returns| annotation_name(returns) == "bool") =>
            {
                let name = item.name.to_string();
                Some(json!({
                    "name": name.clone(),
                    "scope": "module",
                    "returns_boolean": true,
                    "reference": bound(source, module, &name, item.name.range()),
                }))
            }
            _ => None,
        })
        .collect();
    let declared = [assignments, predicates].concat();
    json!({"symbols": declared})
}

/// Return every name one file binds by assignment, with the scope the binding sits in.
fn scoped_assignments(
    module: &ModModule,
) -> Vec<(&'static str, String, ruff_text_size::TextRange)> {
    let mut found = Vec::new();
    let mut pending: Vec<(&'static str, &Stmt)> = module
        .body
        .iter()
        .rev()
        .map(|held| ("module", held))
        .collect();
    while let Some((scope, statement)) = pending.pop() {
        let targets = match statement {
            Stmt::Assign(item) => item.targets.iter().collect::<Vec<_>>(),
            Stmt::AnnAssign(item) => vec![item.target.as_ref()],
            _ => Vec::new(),
        };
        found.extend(targets.into_iter().filter_map(|target| match target {
            Expr::Name(name) => Some((scope, name.id.to_string(), name.range())),
            _ => None,
        }));
        let inner = match statement {
            Stmt::ClassDef(_) => "class",
            Stmt::FunctionDef(_) => "local",
            _ => scope,
        };
        for block in blocks(statement) {
            pending.extend(block.iter().rev().map(|held| (inner, held)));
        }
    }
    found
}

/// Address one declaration together with every reference to it this file states.
///
/// A rename has to edit the declaration and every use together or not at all, so it needs both
/// addressed rather than counted. Whether these are *every* reference is a separate question, and
/// one this file alone can only answer for a name nothing outside it can see.
fn bound(
    source: &Source,
    module: &ModModule,
    name: &str,
    declaration: ruff_text_size::TextRange,
) -> Value {
    let mut found = Vec::new();
    for statement in &module.body {
        collect_loads(source, statement, name, &mut found);
    }
    json!({
        "id": format!("{}:{name}", source.relative),
        "name": name,
        "declaration": source.node("name", declaration),
        "references": found,
        "are_references_complete": names_are_reachable(module) && !name.starts_with("__"),
    })
}

fn collect_loads(source: &Source, statement: &Stmt, name: &str, found: &mut Vec<Value>) {
    for expression in expressions(statement) {
        collect_name_loads(source, expression, name, found);
    }
    for block in blocks(statement) {
        for held in block {
            collect_loads(source, held, name, found);
        }
    }
}

fn collect_name_loads(source: &Source, expression: &Expr, name: &str, found: &mut Vec<Value>) {
    if let Expr::Name(item) = expression
        && item.id.as_str() == name
        && item.ctx.is_load()
    {
        found.push(
            serde_json::to_value(source.node("name", item.range()))
                .expect("a source node must serialize"),
        );
    }
    for child in children(expression) {
        collect_name_loads(source, child, name, found);
    }
}

/// Whether this file is the whole world for the names it declares privately.
///
/// A module-private name can only be reached from inside its own file, so reading the file reads
/// every reference. Two things break that. A name reached by string, through `getattr` or the
/// module dictionary, leaves no reference to find, and a re-export hands the name to callers this
/// file never sees. Where either appears, nothing here claims to have found everything.
fn names_are_reachable(module: &ModModule) -> bool {
    let mut reachable = true;
    for statement in &module.body {
        if let Stmt::Assign(item) = statement
            && item
                .targets
                .iter()
                .any(|target| matches!(target, Expr::Name(name) if name.id.as_str() == "__all__"))
        {
            reachable = false;
        }
        if names_dynamically(statement) {
            reachable = false;
        }
    }
    reachable
}

/// Whether one statement reaches a name by string rather than by writing it.
fn names_dynamically(statement: &Stmt) -> bool {
    const DYNAMIC: &[&str] = &["getattr", "setattr", "globals", "vars", "eval", "exec"];
    let named = expressions(statement)
        .into_iter()
        .flat_map(walk_expression)
        .any(|expression| {
            matches!(expression, Expr::Call(call)
                if DYNAMIC.contains(&qualified_name(&call.func).as_str()))
        });
    named
        || blocks(statement)
            .into_iter()
            .flatten()
            .any(names_dynamically)
}

/// Return one expression and every expression under it.
pub(super) fn walk_expression(expression: &Expr) -> Vec<&Expr> {
    let mut found = vec![expression];
    for child in children(expression) {
        found.extend(walk_expression(child));
    }
    found
}
