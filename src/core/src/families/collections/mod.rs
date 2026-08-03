use crate::source::Source;
use crate::walk::{blocks, children, expressions, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeSet;

/// Every local literal collection one file builds, with the reads that fix its representation.
///
/// A representation is interchangeable only where every read of the binding proves it, so this
/// reads one callable at a time. A module constant is not a candidate at all, because its readers
/// are every file that imports it and this file cannot see them.
pub fn collections(source: &Source, module: &ModModule) -> Value {
    let bodies: Vec<&[Stmt]> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => Some(item.body.as_slice()),
            _ => None,
        })
        .collect();
    json!({
        "pair_sequences": bodies
            .iter()
            .flat_map(|body| pair_sequences(source, body))
            .collect::<Vec<_>>(),
        "local_collections": bodies
            .iter()
            .flat_map(|body| local_collections(source, body))
            .collect::<Vec<_>>(),
    })
}

/// Return the fixed pair tables one callable body binds, with the reads that fix their shape.
///
/// A table of pairs whose every read looks one key up is a dictionary written as a sequence, and
/// the proof is the same one a representation needs, which is every read of a name one body binds.
fn pair_sequences(source: &Source, body: &[Stmt]) -> Vec<Value> {
    let statements = owned(body);
    statements
        .iter()
        .filter_map(|statement| {
            let Stmt::Assign(item) = statement else {
                return None;
            };
            let [Expr::Name(target)] = item.targets.as_slice() else {
                return None;
            };
            let elements = match item.value.as_ref() {
                Expr::List(list) => &list.elts,
                Expr::Tuple(tuple) => &tuple.elts,
                _ => return None,
            };
            let keys: Vec<&Expr> = elements.iter().filter_map(pair_key).collect();
            if keys.is_empty() || keys.len() != elements.len() {
                return None;
            }
            let reads = Reads::of(&statements, target.id.as_str());
            let kinds: Vec<Option<&str>> = keys.iter().map(|key| literal_kind(key)).collect();
            let texts: Vec<&str> = keys.iter().map(|key| source.slice(key.range())).collect();
            Some(json!({
                "pair_count": elements.len(),
                "keys_are_unique_literals": kinds
                    .iter()
                    .all(|held| *held == kinds[0] && held.is_some())
                    && texts.iter().collect::<BTreeSet<_>>().len() == texts.len(),
                "has_single_assignment": reads.stores == 1,
                "all_reads_are_lookup_loops": reads.loads > 0 && reads.loads == reads.lookup,
            }))
        })
        .collect()
}

/// Return the key one element states, when the element is a pair the source writes out.
fn pair_key(element: &Expr) -> Option<&Expr> {
    match element {
        Expr::Tuple(item) if item.elts.len() == 2 => item.elts.first(),
        _ => None,
    }
}

/// Whether one loop does nothing but hand back the value sitting beside a key it matched.
///
/// That is the shape a dictionary lookup replaces exactly. A loop comparing the key twice, running
/// anything after the branch, or falling through to an `else` is doing something a mapping does
/// not, so it leaves the sequence alone.
fn is_lookup_loop(item: &ruff_python_ast::StmtFor) -> bool {
    let Expr::Tuple(target) = item.target.as_ref() else {
        return false;
    };
    let [Expr::Name(key), Expr::Name(value)] = target.elts.as_slice() else {
        return false;
    };
    let [Stmt::If(branch)] = item.body.as_slice() else {
        return false;
    };
    let Expr::Compare(test) = branch.test.as_ref() else {
        return false;
    };
    if !branch.elif_else_clauses.is_empty()
        || !item.orelse.is_empty()
        || !matches!(test.ops.as_ref(), [ruff_python_ast::CmpOp::Eq])
        || !is_named(&test.left, key.id.as_str())
    {
        return false;
    }
    matches!(branch.body.as_slice(), [Stmt::Return(held)]
        if held.value.as_deref().is_some_and(|held| is_named(held, value.id.as_str())))
}

/// Return the local literal collections one callable body binds exactly once.
fn local_collections(source: &Source, body: &[Stmt]) -> Vec<Value> {
    let statements = owned(body);
    statements
        .iter()
        .filter_map(|statement| {
            let Stmt::Assign(item) = statement else {
                return None;
            };
            let [Expr::Name(target)] = item.targets.as_slice() else {
                return None;
            };
            let (kind, elements) = match item.value.as_ref() {
                Expr::List(list) => ("list", &list.elts),
                Expr::Tuple(tuple) => ("tuple", &tuple.elts),
                _ => return None,
            };
            let name = target.id.as_str();
            let reads = Reads::of(&statements, name);
            if reads.stores != 1 {
                return None;
            }
            let texts: Vec<&str> = elements
                .iter()
                .map(|element| source.slice(element.range()))
                .collect();
            let kinds: Vec<Option<&str>> = elements.iter().map(|e| literal_kind(e)).collect();
            Some(json!({
                "name": name,
                "kind": kind,
                "value_count": elements.len(),
                "has_homogeneous_literals": !kinds.is_empty()
                    && kinds.iter().all(|held| *held == kinds[0] && held.is_some()),
                "all_reads_are_iteration": reads.loads > 0 && reads.loads == reads.iteration,
                "all_reads_are_membership": reads.loads > 0 && reads.loads == reads.membership,
                "values_are_unique": texts.iter().collect::<BTreeSet<_>>().len()
                    == texts.len(),
            }))
        })
        .collect()
}

/// How one callable uses a name it binds, counted by the shapes that fix a representation.
///
/// A load neither iterated over nor tested for membership is representation sensitive, whichever
/// shape it takes, so counting the two provable shapes against every load is what lets a rule
/// abstain on indexing, unpacking, mutation, and everything else without naming any of them. A
/// lookup loop is a third and narrower shape, since every one of them is also an iteration.
#[derive(Default)]
struct Reads {
    stores: usize,
    loads: usize,
    iteration: usize,
    membership: usize,
    lookup: usize,
}

impl Reads {
    fn of(statements: &[&Stmt], name: &str) -> Self {
        let mut counted = Self::default();
        for statement in statements {
            if let Stmt::For(item) = statement
                && is_named(&item.iter, name)
            {
                counted.iteration += 1;
                counted.lookup += usize::from(is_lookup_loop(item));
            }
            for expression in stated(statement) {
                counted.count(expression, name);
            }
        }
        counted
    }

    fn count(&mut self, expression: &Expr, name: &str) {
        match expression {
            Expr::Name(item) if item.id.as_str() == name && item.ctx.is_load() => self.loads += 1,
            Expr::Name(item) if item.id.as_str() == name => self.stores += 1,
            Expr::Compare(item)
                if is_membership(&item.ops)
                    && matches!(item.comparators.as_ref(), [held] if is_named(held, name)) =>
            {
                self.membership += 1;
            }
            _ => {
                for generator in comprehension_clauses(expression) {
                    if is_named(&generator.iter, name) {
                        self.iteration += 1;
                    }
                }
            }
        }
        for child in children(expression) {
            self.count(child, name);
        }
    }
}

pub(super) fn is_named(expression: &Expr, name: &str) -> bool {
    matches!(expression, Expr::Name(item) if item.id.as_str() == name)
}

/// Whether one comparison asks for membership rather than any other relation.
pub(super) fn is_membership(operators: &[ruff_python_ast::CmpOp]) -> bool {
    use ruff_python_ast::CmpOp;
    matches!(operators, [CmpOp::In] | [CmpOp::NotIn]) // codespell:ignore
}

pub(super) fn comprehension_clauses(expression: &Expr) -> &[ruff_python_ast::Comprehension] {
    match expression {
        Expr::ListComp(item) => &item.generators,
        Expr::SetComp(item) => &item.generators,
        Expr::DictComp(item) => &item.generators,
        Expr::Generator(item) => &item.generators,
        _ => &[],
    }
}

/// Return every statement one callable owns, stopping at a nested declaration's own body.
///
/// A nested function is a scope of its own, so the names it binds and reads answer for it rather
/// than for the callable holding it, and `walk` reaches that body separately.
pub(super) fn owned(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        if matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            continue;
        }
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Return every expression one statement holds, including the targets it binds.
///
/// `expressions` answers what a statement evaluates, which deliberately leaves out what it assigns
/// to. Counting how often a name is bound needs both sides.
pub(super) fn stated(statement: &Stmt) -> Vec<&Expr> {
    let mut found = expressions(statement);
    match statement {
        Stmt::Assign(item) => found.extend(item.targets.iter()),
        Stmt::AnnAssign(item) => found.push(item.target.as_ref()),
        Stmt::AugAssign(item) => found.push(item.target.as_ref()),
        Stmt::With(item) => found.extend(
            item.items
                .iter()
                .filter_map(|entry| entry.optional_vars.as_deref()),
        ),
        _ => {}
    }
    found
}

/// Name the shape one expression carries when the source states it literally.
pub(super) fn literal_kind(expression: &Expr) -> Option<&'static str> {
    match expression {
        Expr::StringLiteral(_) => Some("string"),
        Expr::NumberLiteral(_) => Some("number"),
        Expr::BooleanLiteral(_) => Some("boolean"),
        Expr::NoneLiteral(_) => Some("none"),
        Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) => Some("sequence"),
        Expr::Dict(_) => Some("mapping"),
        _ => None,
    }
}
