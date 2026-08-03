use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use std::collections::BTreeSet;

use super::expressions::children;
use super::traversal::statements;

pub fn annotation_name(annotation: &Expr) -> String {
    match annotation {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => attribute.attr.to_string(),
        Expr::StringLiteral(literal) => literal.value.to_str().to_string(),
        Expr::Subscript(subscript) => annotation_name(&subscript.value),
        Expr::NoneLiteral(_) => "None".to_string(),
        _ => String::new(),
    }
}

/// Return every field one class declares directly through annotations or receiver assignments.
pub fn class_instance_fields(item: &StmtClassDef) -> BTreeSet<String> {
    item.body.iter().flat_map(class_member_fields).collect()
}

fn class_member_fields(member: &Stmt) -> Vec<String> {
    match member {
        Stmt::AnnAssign(assignment) => annotated_field(assignment).into_iter().collect(),
        Stmt::FunctionDef(method) => statements(&method.body)
            .into_iter()
            .flat_map(assignment_targets)
            .filter_map(receiver_field)
            .collect(),
        _ => Vec::new(),
    }
}

fn annotated_field(assignment: &ruff_python_ast::StmtAnnAssign) -> Option<String> {
    let Expr::Name(name) = assignment.target.as_ref() else {
        return None;
    };
    (annotation_name(&assignment.annotation) != "ClassVar"
        && name.id.chars().any(char::is_lowercase))
    .then(|| name.id.to_string())
}

fn assignment_targets(statement: &Stmt) -> Vec<&Expr> {
    match statement {
        Stmt::Assign(assignment) => assignment.targets.iter().collect(),
        Stmt::AnnAssign(assignment) => vec![assignment.target.as_ref()],
        Stmt::AugAssign(assignment) => vec![assignment.target.as_ref()],
        _ => Vec::new(),
    }
}

/// Return the first instance field one assignment target reaches through `self`.
fn receiver_field(expression: &Expr) -> Option<String> {
    match expression {
        Expr::Attribute(attribute) => match attribute.value.as_ref() {
            Expr::Name(receiver) if receiver.id == "self" => Some(attribute.attr.to_string()),
            nested => receiver_field(nested),
        },
        _ => children(expression).into_iter().find_map(receiver_field),
    }
}
