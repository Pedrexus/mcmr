use super::try_blocks::is_literal;
use crate::source::Source;
use crate::walk::{qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use serde_json::{Value, json};

enum SubjectRead {
    Only,
    Wider,
}

/// Every chain of conditions one file tests in sequence against one subject.
pub fn branches(source: &Source, module: &ModModule) -> Value {
    let chains: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::If(item) => conditional_chain(source, statement, item),
            _ => None,
        })
        .collect();
    json!({"chains": chains})
}

fn conditional_chain(
    source: &Source,
    statement: &Stmt,
    item: &ruff_python_ast::StmtIf,
) -> Option<Value> {
    let (subject, first) = subject_arm(&item.test, &item.body)?;
    let mut arms = vec![first];
    let mut fallback = false;
    for clause in &item.elif_else_clauses {
        match clause.test.as_ref() {
            Some(test) => arms.push(match subject_arm(test, &clause.body) {
                Some((named, arm)) if named == subject => arm,
                _ => wider_arm(&clause.body),
            }),
            None => fallback = true,
        }
    }
    Some(json!({
        "subject": subject,
        "arms": arms,
        "has_fallback": fallback,
        "node": source.node_of("if", statement),
    }))
}

/// Return the subject and arm one test declares, when it compares that subject to a literal.
///
/// The body travels with the test because what an arm does is half of what makes a chain
/// replaceable. A chain whose every arm hands back a value is a table written as control flow,
/// while one whose arms run several statements each is branching that happens to key on a literal.
fn subject_arm(test: &Expr, body: &[Stmt]) -> Option<(String, Value)> {
    let Expr::Compare(compare) = test else {
        return None;
    };
    let [operator] = compare.ops.as_ref() else {
        return None;
    };
    let [comparator] = compare.comparators.as_ref() else {
        return None;
    };
    let subject = qualified_name(&compare.left);
    if subject.is_empty() || !is_literal(comparator) {
        return None;
    }
    Some((
        subject,
        arm(
            comparison_name(operator),
            literal_text(comparator),
            body,
            SubjectRead::Only,
        ),
    ))
}

/// Return the arm one test declares when it reads more than the subject the chain keys on.
///
/// Such an arm has to stay in the chain rather than end it, because a rule replacing a chain with
/// a table needs to see that one arm asks a second question and refuse the whole chain.
fn wider_arm(body: &[Stmt]) -> Value {
    arm("wider", String::new(), body, SubjectRead::Wider)
}

fn arm(comparison: &str, literal: String, body: &[Stmt], subject_read: SubjectRead) -> Value {
    json!({
        "comparison": comparison,
        "literal": literal,
        "statement_count": body.len(),
        "returns_value": matches!(body.last(), Some(Stmt::Return(held)) if held.value.is_some()),
        "reads_subject_only": matches!(subject_read, SubjectRead::Only),
    })
}

fn comparison_name(operator: &ruff_python_ast::CmpOp) -> &'static str {
    use ruff_python_ast::CmpOp;
    match operator {
        CmpOp::Eq => "equals",
        CmpOp::NotEq => "differs",
        CmpOp::Is => "identity",
        CmpOp::IsNot => "not_identity",
        CmpOp::In => "membership",
        CmpOp::NotIn => "not_membership", // codespell:ignore
        _ => "ordering",
    }
}

pub(super) fn literal_text(expression: &Expr) -> String {
    match expression {
        Expr::StringLiteral(item) => item.value.to_str().to_string(),
        Expr::NumberLiteral(item) => format!("{:?}", item.value),
        Expr::BooleanLiteral(item) => item.value.to_string(),
        _ => String::new(),
    }
}
