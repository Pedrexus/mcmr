use crate::families::collections::{is_membership, is_named, stated};
use crate::walk::{children, statements};
use ruff_python_ast::{Expr, Stmt};
use std::collections::BTreeSet;

mod calls;
mod comprehensions;

use calls::recognize_call;
use comprehensions::recognize_comprehension;

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
            held.retain(|expression| !is_named(expression, name));
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
        for child in self.recognize(expression, name) {
            self.read(child, name);
        }
    }

    fn recognize<'source>(&mut self, expression: &'source Expr, name: &str) -> Vec<&'source Expr> {
        match expression {
            Expr::Attribute(item) if is_named(&item.value, name) => {
                self.attributes.push(item.attr.to_string());
                Vec::new()
            }
            Expr::Subscript(item) if is_named(&item.value, name) => {
                self.operations.insert("getitem".to_string());
                vec![item.slice.as_ref()]
            }
            Expr::Call(item) => recognize_call(self, item, name),
            Expr::Compare(item)
                if is_membership(&item.ops)
                    && item.comparators.iter().any(|held| is_named(held, name)) =>
            {
                self.operations.insert("contains".to_string());
                vec![item.left.as_ref()]
            }
            Expr::BinOp(item) if is_named(&item.left, name) || is_named(&item.right, name) => {
                self.operations.insert("arithmetic".to_string());
                Vec::new()
            }
            Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
                recognize_comprehension(self, expression, name)
            }
            _ => children(expression),
        }
    }
}
