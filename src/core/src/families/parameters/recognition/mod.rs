use crate::families::collections::{is_membership, is_named, stated};
use crate::walk::{children, qualified_name, statements};
use ruff_python_ast::{Expr, Stmt};
use std::collections::BTreeSet;

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

/// What one body does with a name it did not bind, and whether every use of it was recognized.
#[derive(Default)]
pub(in crate::families) struct Uses {
    pub(in crate::families) operations: BTreeSet<String>,
    pub(in crate::families) attributes: Vec<String>,
    pub(in crate::families) returned: bool,
    pub(in crate::families) unrecognized: usize,
}

impl Uses {
    pub(in crate::families) fn read_body(&mut self, body: &[Stmt], name: &str) {
        for statement in statements(body) {
            let mut held = stated(statement);
            match statement {
                Stmt::Return(item)
                    if item
                        .value
                        .as_deref()
                        .is_some_and(|held| is_named(held, name)) =>
                {
                    self.returned = true;
                }
                Stmt::For(item) if is_named(&item.iter, name) => {
                    self.operations.insert("iter".to_string());
                }
                _ => {}
            }
            let written = self.read_writes(statement, name);
            held.retain(|expression| {
                !is_named(expression, name)
                    && !written
                        .iter()
                        .any(|target| std::ptr::eq(*target, *expression))
            });
            for expression in held {
                self.read(expression, name);
            }
        }
    }

    fn read(&mut self, expression: &Expr, name: &str) {
        if is_named(expression, name) {
            self.unrecognized += 1;
            return;
        }
        match expression {
            Expr::Attribute(item) if is_named(&item.value, name) => {
                self.attributes.push(item.attr.to_string());
            }
            Expr::Subscript(item) if is_named(&item.value, name) => {
                self.operations.insert("getitem".to_string());
                self.read(&item.slice, name);
            }
            Expr::Call(item) => self.read_call(item, name),
            Expr::Compare(item)
                if is_membership(&item.ops)
                    && item.comparators.iter().any(|held| is_named(held, name)) =>
            {
                self.operations.insert("contains".to_string());
                self.read(&item.left, name);
            }
            Expr::BinOp(item) if is_named(&item.left, name) || is_named(&item.right, name) => {
                self.operations.insert("arithmetic".to_string());
            }
            Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
                self.read_comprehension(expression, name);
            }
            _ => {
                for child in children(expression) {
                    self.read(child, name);
                }
            }
        }
    }

    fn read_call(&mut self, item: &ruff_python_ast::ExprCall, name: &str) {
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
            self.operations.insert(method.attr.to_string());
        } else if READING_BUILTINS.contains(&called.as_str())
            && item.arguments.args.iter().any(|held| is_named(held, name))
        {
            self.operations.insert(called);
            remaining.retain(|held| !is_named(held, name));
        } else {
            remaining.push(item.func.as_ref());
        }
        for expression in remaining {
            self.read(expression, name);
        }
    }

    fn read_comprehension(&mut self, expression: &Expr, name: &str) {
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
        for generator in crate::families::collections::comprehension_clauses(expression) {
            if is_named(&generator.iter, name) {
                self.operations.insert("iter".to_string());
            } else {
                remaining.push(&generator.iter);
            }
            remaining.extend(generator.ifs.iter());
        }
        for expression in remaining {
            self.read(expression, name);
        }
    }
    /// Record what one statement writes through a subscript of the name, and return those targets.
    ///
    /// `values[key] = held` and `del values[key]` reach `__setitem__` and `__delitem__`, so they
    /// are mutations rather than the lookup the same expression reads as on the right of an
    /// assignment. The consumed targets travel back so the generic read never counts them twice.
    fn read_writes<'held>(&mut self, statement: &'held Stmt, name: &str) -> Vec<&'held Expr> {
        let (targets, operation): (Vec<&Expr>, &str) = match statement {
            Stmt::Assign(item) => (item.targets.iter().collect(), "setitem"),
            Stmt::AnnAssign(item) => (vec![item.target.as_ref()], "setitem"),
            Stmt::AugAssign(item) => (vec![item.target.as_ref()], "setitem"),
            Stmt::Delete(item) => (item.targets.iter().collect(), "delitem"),
            _ => return Vec::new(),
        };
        let written = targets
            .into_iter()
            .filter(
                |target| matches!(target, Expr::Subscript(item) if is_named(&item.value, name)),
            )
            .collect::<Vec<_>>();
        for target in &written {
            self.operations.insert(operation.to_string());
            if let Expr::Subscript(item) = target {
                self.read(&item.slice, name);
            }
        }
        written
    }
}
