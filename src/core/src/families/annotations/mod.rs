use crate::source::Source;
use crate::walk::{annotation_name, children, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

mod declared;
mod role;

use declared::DeclaredAnnotation;
use role::AnnotationRole;

/// Every resolved annotation one file declares, with the union members it names.
pub fn annotations(source: &Source, module: &ModModule) -> Value {
    let declared: Vec<Value> = walk(module)
        .into_iter()
        .flat_map(annotation_expressions)
        .map(|declared| {
            let recipe = constrained_annotation(declared.expression)
                .map(|expression| source.slice(expression.range()))
                .unwrap_or_default();
            json!({
                "path": source.relative.clone(),
                "union_members": union_members(declared.expression),
                "resolved_names": [annotation_name(declared.expression)],
                "constraint_recipe": recipe,
                "is_field_specific_metadata": describes_one_field(declared.expression),
                "role": declared.role.as_str(),
                "is_external_boundary": declared.is_external_boundary,
                "node": source.node_of("annotation", declared.expression),
            })
        })
        .collect();
    json!({"annotations": declared})
}

/// Return the reusable `Annotated` expression inside one annotation when it carries constraints.
fn constrained_annotation(annotation: &Expr) -> Option<&Expr> {
    if let Expr::Subscript(item) = annotation
        && annotation_name(&item.value) == "Annotated"
        && matches!(item.slice.as_ref(), Expr::Tuple(arguments)
            if arguments.elts.iter().skip(1).any(constraint_metadata))
    {
        return Some(annotation);
    }
    children(annotation)
        .into_iter()
        .find_map(constrained_annotation)
}

/// Whether one `Annotated` metadata expression is a reusable validation constraint.
fn constraint_metadata(expression: &Expr) -> bool {
    const CONSTRAINTS: &[&str] = &[
        "AfterValidator",
        "BeforeValidator",
        "Field",
        "Ge",
        "Gt",
        "Interval",
        "Le",
        "Len",
        "Lt",
        "MaxLen",
        "MinLen",
        "MultipleOf",
        "PlainSerializer",
        "PlainValidator",
        "Predicate",
        "StringConstraints",
        "UrlConstraints",
        "WrapSerializer",
        "WrapValidator",
    ];
    qualified_name(expression)
        .rsplit('.')
        .next()
        .is_some_and(|name| CONSTRAINTS.contains(&name))
}

/// Whether one annotation carries metadata that belongs to the single field declaring it.
///
/// A constraint travels to every field that needs the same shape, while a description, a title, an
/// alias, or an example is written about one field and reads as noise anywhere else. Grouping the
/// two together would propose an alias for a recipe nobody else can reuse.
fn describes_one_field(annotation: &Expr) -> bool {
    const DESCRIBING: &[&str] = &[
        "description",
        "title",
        "alias",
        "validation_alias",
        "serialization_alias",
        "examples",
        "json_schema_extra",
        "deprecated",
    ];
    let mut pending = vec![annotation];
    while let Some(expression) = pending.pop() {
        if let Expr::Call(item) = expression
            && item.arguments.keywords.iter().any(|keyword| {
                keyword
                    .arg
                    .as_ref()
                    .is_some_and(|named| DESCRIBING.contains(&named.as_str()))
            })
        {
            return true;
        }
        pending.extend(children(expression));
    }
    false
}

fn annotation_expressions(statement: &Stmt) -> Vec<DeclaredAnnotation<'_>> {
    match statement {
        Stmt::AnnAssign(item) => vec![DeclaredAnnotation {
            expression: item.annotation.as_ref(),
            role: AnnotationRole::Variable,
            is_external_boundary: false,
        }],
        Stmt::TypeAlias(item) => vec![DeclaredAnnotation {
            expression: item.value.as_ref(),
            role: AnnotationRole::Alias,
            is_external_boundary: false,
        }],
        Stmt::FunctionDef(item) => {
            let is_external_boundary = item.decorator_list.iter().any(|decorator| {
                matches!(
                    qualified_name(&decorator.expression).rsplit('.').next(),
                    Some("command" | "callback")
                )
            });
            item.returns
                .iter()
                .map(|expression| DeclaredAnnotation {
                    expression,
                    role: AnnotationRole::Return,
                    is_external_boundary,
                })
                .chain(item.parameters.iter().filter_map(|parameter| {
                    parameter.annotation().map(|expression| DeclaredAnnotation {
                        expression,
                        role: AnnotationRole::Parameter,
                        is_external_boundary,
                    })
                }))
                .collect()
        }
        _ => Vec::new(),
    }
}

fn union_members(annotation: &Expr) -> Vec<String> {
    match annotation {
        Expr::BinOp(item) => [union_members(&item.left), union_members(&item.right)].concat(),
        _ => vec![annotation_name(annotation)],
    }
}
