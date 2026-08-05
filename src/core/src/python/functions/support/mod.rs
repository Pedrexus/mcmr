use super::asyncio::Asyncio;
use crate::functions::FunctionParameter;
use crate::source::Source;
use crate::walk::{annotation_name, children, docstring};
use ruff_python_ast::{Expr, ModModule, Parameters, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::Ranged;
use std::collections::BTreeSet;

mod control;
mod vocabulary;

pub(super) use control::control_increments;
pub(in crate::python) use vocabulary::MODEL_FOUNDATIONS;
pub(super) use vocabulary::{
    BINDING_DECORATORS, DTYPE_WORDS, LIFECYCLE_NAMES, TENSOR_ANNOTATIONS, TENSOR_TYPES,
    VALIDATION_EXCEPTIONS, VALIDATOR_DECORATORS,
};
pub(in crate::python) use vocabulary::{
    PythonName, base_name, decorator_name, is_protocol_name, root_name,
};
use vocabulary::{TensorOrigins, is_tensor_library, tensor_origins};

/// What the file around a callable already answered, read once rather than once per callable.
pub(super) struct ModuleContext {
    pub(super) asyncio: Asyncio,
    tensor_origins: TensorOrigins,
}

impl ModuleContext {
    pub(super) fn of(module: &ModModule) -> Self {
        Self {
            asyncio: Asyncio::of(module),
            tensor_origins: tensor_origins(module),
        }
    }

    /// Whether one annotation names a value carrying a shape and an element type.
    pub(super) fn is_tensor_annotation(&self, annotation: &Expr) -> bool {
        let mut held = Vec::new();
        descend(annotation, &mut held);
        held.iter().any(|expression| {
            TENSOR_TYPES.contains(&annotation_name(expression).as_str())
                && is_tensor_library(&self.tensor_origins, expression)
        }) || self.tensor_wrapper(annotation).is_some()
    }

    /// Return the jaxtyping wrapper one annotation states, which names a dtype and a shape at once.
    pub(super) fn tensor_wrapper(&self, annotation: &Expr) -> Option<String> {
        let Expr::Subscript(item) = annotation else {
            return None;
        };
        let named = annotation_name(&item.value);
        let mut held = Vec::new();
        descend(&item.slice, &mut held);
        let states_dimensions = held
            .iter()
            .any(|inner| matches!(inner, Expr::StringLiteral(_)));
        (TENSOR_ANNOTATIONS.contains(&named.as_str())
            && states_dimensions
            && is_tensor_library(&self.tensor_origins, &item.value))
        .then_some(named)
    }
}

/// Names a decorator carries to say how the language binds a member rather than who calls it.
/// Return the single expression one body evaluates, when the body is exactly that.
pub(super) fn body_expression(source: &Source, body: &[Stmt]) -> Option<crate::protocol::Node> {
    match body {
        [Stmt::Return(item)] => item
            .value
            .as_ref()
            .map(|value| source.node("expression", value.range())),
        [Stmt::Expr(item)] => Some(source.node("expression", item.value.range())),
        _ => None,
    }
}

/// Return the body one callable runs, without the docstring that opens it.
pub(in crate::python) fn executable(body: &[Stmt]) -> &[Stmt] {
    match body {
        [first, rest @ ..] if docstring(std::slice::from_ref(first)).is_some() => rest,
        _ => body,
    }
}

/// Collect one expression and every expression inside it.
pub(in crate::python) fn descend<'a>(expression: &'a Expr, found: &mut Vec<&'a Expr>) {
    found.push(expression);
    for child in children(expression) {
        descend(child, found);
    }
}

/// Whether one callable promises a lazy table expression or a rule query rather than executing it.
pub(super) fn returns_query_plan(item: &StmtFunctionDef) -> bool {
    let Some(annotation) = item.returns.as_deref() else {
        return false;
    };
    let mut annotations = Vec::new();
    descend(annotation, &mut annotations);
    annotations.iter().any(|expression| {
        let name = annotation_name(expression);
        matches!(name.as_str(), "Expr" | "LazyFrame") || name.ends_with("Query")
    })
}

/// Whether one expression does something rather than merely naming something.
pub(super) fn is_behavior(expression: &Expr) -> bool {
    matches!(
        expression,
        Expr::Await(_)
            | Expr::BinOp(_)
            | Expr::BoolOp(_)
            | Expr::Call(_)
            | Expr::Compare(_)
            | Expr::DictComp(_)
            | Expr::Generator(_)
            | Expr::If(_)
            | Expr::ListComp(_)
            | Expr::Named(_)
            | Expr::SetComp(_)
            | Expr::UnaryOp(_)
            | Expr::Yield(_)
            | Expr::YieldFrom(_)
    )
}

/// Return the exact text of every decorator one declaration wears.
pub(in crate::python) fn decorator_texts(
    source: &Source,
    decorators: &[ruff_python_ast::Decorator],
) -> Vec<String> {
    decorators
        .iter()
        .map(|decorator| source.slice(decorator.expression.range()).to_string())
        .collect()
}

/// Return what one decorator is called, without the module that owns it or the arguments it took.
/// Return the plain name of every base one class states, without a module path or a type argument.
pub(in crate::python) fn base_names(source: &Source, item: &StmtClassDef) -> Vec<String> {
    item.arguments
        .as_ref()
        .map(|arguments| {
            arguments
                .args
                .iter()
                .map(|argument| base_name(source.slice(argument.range())).to_string())
                .collect()
        })
        .unwrap_or_default()
}

/// Return what one base is called, without its module path, its type arguments, or its call.
/// Return the name one expression is rooted in, which is the object every access starts from.
/// Whether an expression reads receiver-owned state rather than a sibling method.
pub(in crate::python) fn receiver_state(
    expression: &Expr,
    receiver: &str,
    methods: &BTreeSet<&str>,
) -> bool {
    if let Expr::Attribute(attribute) = expression
        && root_name(&attribute.value) == receiver
    {
        return !methods.contains(attribute.attr.as_str());
    }
    if matches!(expression, Expr::Name(name) if name.id.as_str() == receiver) {
        return receiver != "cls";
    }
    children(expression)
        .into_iter()
        .any(|child| receiver_state(child, receiver, methods))
}

pub(super) fn parameters(source: &Source, parameters: &Parameters) -> Vec<FunctionParameter> {
    let mut declared = Vec::new();
    for (index, parameter) in parameters.posonlyargs.iter().enumerate() {
        let mut fact = parameter_fact(source, parameter);
        fact.contract.is_positional_only = true;
        fact.contract.is_receiver = index == 0 && matches!(fact.name.as_str(), "self" | "cls");
        fact.contract.is_required_by_external_contract =
            !fact.contract.is_receiver && parameter.default().is_none();
        declared.push(fact);
    }
    let offset = parameters.posonlyargs.len();
    for (index, parameter) in parameters.args.iter().enumerate() {
        let mut fact = parameter_fact(source, parameter);
        fact.contract.is_receiver =
            offset == 0 && index == 0 && matches!(fact.name.as_str(), "self" | "cls");
        fact.contract.is_required_by_external_contract =
            !fact.contract.is_receiver && parameter.default().is_none();
        declared.push(fact);
    }
    for parameter in &parameters.kwonlyargs {
        let mut fact = parameter_fact(source, parameter);
        fact.contract.is_keyword_only = true;
        declared.push(fact);
    }
    declared
}

fn parameter_fact(
    source: &Source,
    declared: &ruff_python_ast::ParameterWithDefault,
) -> FunctionParameter {
    let parameter = &declared.parameter;
    let name = parameter.name.to_string();
    let type_name = parameter
        .annotation
        .as_ref()
        .map(|annotation| {
            source
                .slice(annotation.range())
                .split_whitespace()
                .collect::<String>()
        })
        .unwrap_or_default();
    let has_boolean_annotation = type_name == "bool";
    let mut fact = FunctionParameter::named(name);
    fact.type_name = type_name;
    fact.contract.is_required_by_external_contract = declared.default().is_none();
    fact.contract.has_boolean_annotation = has_boolean_annotation;
    fact.contract.has_boolean_default =
        matches!(declared.default(), Some(Expr::BooleanLiteral(_)));
    fact
}
