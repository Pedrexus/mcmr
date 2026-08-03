use super::imports::{direct_imports, resolve_imported};
use crate::source::Source;
use crate::walk::statements;
use crate::walk::{annotation_name, children, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

mod evidence;
mod validation;
mod variants;

use validation::validator;

/// Every model one file declares that a validator or a constructor shapes.
pub fn pydantic_models(source: &Source, module: &ModModule) -> Value {
    let imports = direct_imports(module);
    let models: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => Some(item),
            _ => None,
        })
        .filter(|item| is_model(item, &imports) || is_plain_class(item))
        .map(|item| {
            let flexible_base = item.arguments.as_ref().and_then(|arguments| {
                arguments.args.iter().find(|base| {
                    resolve_imported(&imports, &qualified_name(base))
                        .rsplit('.')
                        .next()
                        == Some("FrozenFlexModel")
                })
            });
            let fields = model_fields(item, &imports);
            let analyzed_fields = item
                .body
                .iter()
                .filter_map(|member| {
                    let Stmt::AnnAssign(field) = member else {
                        return None;
                    };
                    if is_class_variable(&field.annotation, &imports) {
                        return None;
                    }
                    let Expr::Name(name) = field.target.as_ref() else {
                        return None;
                    };
                    Some(json!({
                        "name": name.id.to_string(),
                        "annotation": source.slice(field.annotation.range()),
                        "span": source.span(field.annotation.range()),
                        "contains_variadic_tuple": contains_variadic_tuple(
                            &field.annotation,
                            &imports,
                        ),
                    }))
                })
                .collect::<Vec<_>>();
            let validators: Vec<Value> = item
                .body
                .iter()
                .filter_map(|member| match member {
                    Stmt::FunctionDef(method) => validator(method, &fields),
                    _ => None,
                })
                .collect();
            let initializers: Vec<&ruff_python_ast::StmtFunctionDef> = item
                .body
                .iter()
                .filter_map(|member| match member {
                    Stmt::FunctionDef(method) if method.name.as_str() == "__init__" => {
                        Some(method)
                    }
                    _ => None,
                })
                .collect();
            let constructed = initializers.first();
            json!({
                "name": item.name.to_string(),
                "fields": analyzed_fields,
                "validators": validators,
                "is_pydantic_model": is_model(item, &imports),
                "uses_flexible_model": flexible_base.is_some(),
                "flexible_base_span": flexible_base.map(|base| source.span(base.range())),
                "is_undecorated_plain_class": is_plain_class(item),
                "synchronous_init_count": initializers
                    .iter()
                    .filter(|method| !method.is_async)
                    .count(),
                "fixed_parameter_count": constructed
                    .map(|method| method.parameters.iter().skip(1).count())
                    .unwrap_or_default(),
                "stored_parameter_count": constructed
                    .map(|method| stored_parameters(method))
                    .unwrap_or_default(),
                "validation_count": constructed
                    .map(|method| {
                        statements(&method.body)
                            .iter()
                            .filter(|held| matches!(held, Stmt::Raise(_) | Stmt::Assert(_)))
                            .count()
                    })
                    .unwrap_or_default(),
                "default_count": constructed
                    .map(|method| {
                        method
                            .parameters
                            .iter()
                            .filter(|parameter| parameter.default().is_some())
                            .count()
                    })
                    .unwrap_or_default(),
                "has_only_data_identity_methods": states_only_data_identity(item),
            })
        })
        .collect();
    json!({"models": models})
}

/// Return directly declared model fields and whether each is an optional field defaulting to none.
fn model_fields(
    item: &ruff_python_ast::StmtClassDef,
    imports: &BTreeMap<String, String>,
) -> BTreeMap<String, bool> {
    item.body
        .iter()
        .filter_map(|member| {
            let Stmt::AnnAssign(field) = member else {
                return None;
            };
            if is_class_variable(&field.annotation, imports) {
                return None;
            }
            let Expr::Name(name) = field.target.as_ref() else {
                return None;
            };
            let optional = (annotation_name(&field.annotation) == "Optional"
                || children(&field.annotation)
                    .into_iter()
                    .chain(std::iter::once(field.annotation.as_ref()))
                    .any(|part| matches!(part, Expr::NoneLiteral(_))))
                && matches!(field.value.as_deref(), Some(Expr::NoneLiteral(_)));
            Some((name.id.to_string(), optional))
        })
        .collect()
}

/// Whether an annotation marks class state rather than one validated model field.
fn is_class_variable(annotation: &Expr, imports: &BTreeMap<String, String>) -> bool {
    let Expr::Subscript(item) = annotation else {
        return false;
    };
    matches!(
        resolve_imported(imports, &qualified_name(&item.value)).as_str(),
        "typing.ClassVar"
    )
}

/// Whether one class derives from something naming itself a model.
fn is_model(item: &ruff_python_ast::StmtClassDef, imports: &BTreeMap<String, String>) -> bool {
    item.arguments.as_ref().is_some_and(|arguments| {
        arguments
            .args
            .iter()
            .any(|base| resolve_imported(imports, &qualified_name(base)).contains("Model"))
    })
}

/// Whether one field annotation contains a homogeneous arbitrary-length tuple.
fn contains_variadic_tuple(annotation: &Expr, imports: &BTreeMap<String, String>) -> bool {
    let direct = match annotation {
        Expr::Subscript(item) => {
            let container = resolve_imported(imports, &qualified_name(&item.value));
            matches!(
                container.as_str(),
                "tuple" | "builtins.tuple" | "typing.Tuple"
            ) && matches!(item.slice.as_ref(), Expr::Tuple(arguments)
                    if matches!(arguments.elts.as_slice(), [_, Expr::EllipsisLiteral(_)]))
        }
        _ => false,
    };
    direct
        || children(annotation)
            .into_iter()
            .any(|child| contains_variadic_tuple(child, imports))
}

/// Whether one class is an ordinary class nothing has already turned into a data holder.
///
/// A base or a decorator is somebody else already answering the question, so a candidate for
/// becoming a model is a class that derives nothing and carries no decorator at all.
fn is_plain_class(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.decorator_list.is_empty()
        && item
            .arguments
            .as_ref()
            .is_none_or(|arguments| arguments.args.is_empty() && arguments.keywords.is_empty())
}

/// Return how many of one initializer's parameters it stores on the receiver unchanged.
fn stored_parameters(method: &ruff_python_ast::StmtFunctionDef) -> usize {
    let names: BTreeSet<&str> = method
        .parameters
        .iter()
        .map(|parameter| parameter.name().as_str())
        .collect();
    let mut stored = BTreeSet::new();
    for statement in statements(&method.body) {
        let Stmt::Assign(item) = statement else {
            continue;
        };
        let Expr::Name(value) = item.value.as_ref() else {
            continue;
        };
        let assigns_receiver = item.targets.iter().any(|target| {
            matches!(target, Expr::Attribute(held)
                if matches!(held.value.as_ref(), Expr::Name(receiver) if receiver.id == "self"))
        });
        if assigns_receiver && names.contains(value.id.as_str()) {
            stored.insert(value.id.as_str());
        }
    }
    stored.len()
}

/// Whether every method one class states beside its initializer is a data identity protocol.
fn states_only_data_identity(item: &ruff_python_ast::StmtClassDef) -> bool {
    const IDENTITY: &[&str] = &[
        "__init__",
        "__eq__",
        "__ne__",
        "__hash__",
        "__repr__",
        "__str__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__post_init__",
    ];
    item.body.iter().all(|member| match member {
        Stmt::FunctionDef(method) => IDENTITY.contains(&method.name.as_str()),
        _ => true,
    })
}
