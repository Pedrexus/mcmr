use crate::source::Source;
use crate::walk::{
    blocks, class_instance_fields, docstring, expression_tree, expressions, qualified_name,
};
use ruff_python_ast::{Expr, ModModule, Stmt, StmtClassDef};
use ruff_text_size::Ranged;

use super::super::contracts::{ClassShape, Declared, Member};

/// Return every top-level class one module declares, read for what a class rule asks of it.
pub(super) fn declarations(source: &Source, module: &ModModule) -> Vec<Declared> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => Some(Declared {
                name: item.name.to_string(),
                span: source.span(item.range()),
                bases: item
                    .arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter())
                    .map(|base| last_segment(&qualified_name(base)).to_string())
                    .collect(),
                line_count: source.line_count(item.range()),
                members: members(item),
                field_count: class_instance_fields(item).len(),
                shape: ClassShape {
                    is_declarative: is_declarative(item),
                    is_plain: item.decorator_list.is_empty()
                        && item
                            .arguments
                            .iter()
                            .all(|arguments| arguments.keywords.is_empty()),
                },
            }),
            _ => None,
        })
        .collect()
}

/// Return every method one class declares, read for whether inheriting it twice is a hazard.
fn members(item: &StmtClassDef) -> Vec<Member> {
    item.body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(method) => Some(method),
            _ => None,
        })
        .map(|method| {
            let marked = method.decorator_list.iter().any(|decorator| {
                matches!(
                    last_segment(&qualified_name(&decorator.expression)),
                    "abstractmethod" | "abstractproperty" | "overload"
                )
            });
            Member {
                name: method.name.to_string(),
                is_concrete: !marked && !is_stub(&method.body),
                delegates_to_super: delegates_to_super(&method.body, method.name.as_str()),
            }
        })
        .collect()
}

/// Whether one class declares data a library validates rather than behavior it runs.
fn is_declarative(item: &StmtClassDef) -> bool {
    item.arguments
        .iter()
        .flat_map(|arguments| arguments.args.iter())
        .any(|base| {
            matches!(
                last_segment(&qualified_name(base)),
                "BaseModel"
                    | "Component"
                    | "DeclarativeBase"
                    | "FlexModel"
                    | "FrozenFlexModel"
                    | "FrozenModel"
                    | "Model"
                    | "RootModel"
                    | "SQLModel"
            )
        })
        || item
            .decorator_list
            .iter()
            .any(|decorator| last_segment(&qualified_name(&decorator.expression)) == "dataclass")
}

/// Whether one body stands in for an implementation rather than being one.
fn is_stub(body: &[Stmt]) -> bool {
    executable(body).iter().all(|statement| match statement {
        Stmt::Pass(_) => true,
        Stmt::Expr(item) => matches!(item.value.as_ref(), Expr::EllipsisLiteral(_)),
        Stmt::Raise(item) => item
            .exc
            .as_deref()
            .is_some_and(|raised| qualified_name(raised).ends_with("NotImplementedError")),
        _ => false,
    })
}

/// Whether one body hands the same member on to whatever the class was linearized behind.
fn delegates_to_super(body: &[Stmt], name: &str) -> bool {
    let mut found = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        for expression in expressions(statement) {
            found.extend(expression_tree(expression));
        }
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    found.into_iter().any(|expression| {
        matches!(expression, Expr::Attribute(item)
            if item.attr.as_str() == name
                && matches!(item.value.as_ref(), Expr::Call(inner)
                    if qualified_name(&inner.func) == "super"))
    })
}

/// Return the body a declaration runs, without the docstring that opens it.
pub(super) fn executable(body: &[Stmt]) -> &[Stmt] {
    match body.split_first() {
        Some((first, rest)) if docstring(std::slice::from_ref(first)).is_some() => rest,
        _ => body,
    }
}

pub(super) fn last_segment(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}
