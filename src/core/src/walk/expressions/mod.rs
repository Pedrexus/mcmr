use ruff_python_ast::{Expr, Parameters, Stmt};

/// Return the expressions one statement evaluates directly.
pub fn expressions(statement: &Stmt) -> Vec<&Expr> {
    match statement {
        Stmt::Expr(item) => vec![item.value.as_ref()],
        Stmt::Assign(item) => vec![item.value.as_ref()],
        Stmt::AnnAssign(item) => {
            let mut inner: Vec<&Expr> = vec![item.annotation.as_ref()];
            inner.extend(item.value.iter().map(AsRef::as_ref));
            inner
        }
        Stmt::AugAssign(item) => vec![item.value.as_ref()],
        Stmt::Return(item) => item.value.iter().map(AsRef::as_ref).collect(),
        Stmt::If(item) => vec![item.test.as_ref()],
        Stmt::While(item) => vec![item.test.as_ref()],
        Stmt::For(item) => vec![item.iter.as_ref(), item.target.as_ref()],
        Stmt::Raise(item) => item.exc.iter().map(AsRef::as_ref).collect(),
        Stmt::Assert(item) => vec![item.test.as_ref()],
        Stmt::Delete(item) => item.targets.iter().collect(),
        Stmt::With(item) => item.items.iter().map(|entry| &entry.context_expr).collect(),
        Stmt::TypeAlias(item) => std::iter::once(item.value.as_ref())
            .chain(type_parameters(statement))
            .collect(),
        Stmt::FunctionDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .chain(item.returns.iter().map(AsRef::as_ref))
            .chain(signature(&item.parameters))
            .chain(type_parameters(statement))
            .collect(),
        Stmt::ClassDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .chain(
                item.arguments
                    .as_ref()
                    .map(|arguments| arguments.args.iter())
                    .into_iter()
                    .flatten(),
            )
            .chain(type_parameters(statement))
            .collect(),
        _ => Vec::new(),
    }
}

/// Return the expressions one expression contains.
pub fn children(expression: &Expr) -> Vec<&Expr> {
    match expression {
        Expr::Call(item) => {
            let mut inner = vec![item.func.as_ref()];
            inner.extend(item.arguments.args.iter());
            inner.extend(item.arguments.keywords.iter().map(|keyword| &keyword.value));
            inner
        }
        Expr::Attribute(item) => vec![item.value.as_ref()],
        Expr::Subscript(item) => vec![item.value.as_ref(), item.slice.as_ref()],
        Expr::BinOp(item) => vec![item.left.as_ref(), item.right.as_ref()],
        Expr::BoolOp(item) => item.values.iter().collect(),
        Expr::UnaryOp(item) => vec![item.operand.as_ref()],
        Expr::Compare(item) => {
            let mut inner = vec![item.left.as_ref()];
            inner.extend(item.comparators.iter());
            inner
        }
        Expr::List(item) => item.elts.iter().collect(),
        Expr::Tuple(item) => item.elts.iter().collect(),
        Expr::Set(item) => item.elts.iter().collect(),
        Expr::Dict(item) => item
            .items
            .iter()
            .flat_map(|entry| entry.key.iter().chain(std::iter::once(&entry.value)))
            .collect(),
        Expr::ListComp(item) => with_clauses(item.elt.as_ref(), &item.generators),
        Expr::SetComp(item) => with_clauses(item.elt.as_ref(), &item.generators),
        Expr::Generator(item) => with_clauses(item.elt.as_ref(), &item.generators),
        Expr::DictComp(item) => {
            let mut inner = vec![item.value.as_ref()];
            inner.extend(item.key.iter().map(AsRef::as_ref));
            inner.extend(clauses(&item.generators));
            inner
        }
        Expr::If(item) => vec![item.test.as_ref(), item.body.as_ref(), item.orelse.as_ref()],
        Expr::Await(item) => vec![item.value.as_ref()],
        Expr::Yield(item) => item.value.iter().map(AsRef::as_ref).collect(),
        Expr::Starred(item) => vec![item.value.as_ref()],
        Expr::Lambda(item) => vec![item.body.as_ref()],
        Expr::Named(item) => vec![item.value.as_ref()],
        Expr::FString(item) => item
            .value
            .elements()
            .filter_map(|element| element.as_interpolation())
            .map(|interpolation| interpolation.expression.as_ref())
            .collect(),
        _ => Vec::new(),
    }
}

fn with_clauses<'a>(
    element: &'a Expr,
    generators: &'a [ruff_python_ast::Comprehension],
) -> Vec<&'a Expr> {
    std::iter::once(element)
        .chain(clauses(generators))
        .collect()
}

/// Return one expression and every expression nested inside it.
pub fn expression_tree(expression: &Expr) -> Vec<&Expr> {
    let mut collected = Vec::new();
    let mut pending = vec![expression];
    while let Some(current) = pending.pop() {
        collected.push(current);
        pending.extend(children(current).into_iter().rev());
    }
    collected
}

fn clauses(generators: &[ruff_python_ast::Comprehension]) -> Vec<&Expr> {
    generators
        .iter()
        .flat_map(|generator| std::iter::once(&generator.iter).chain(generator.ifs.iter()))
        .collect()
}

fn signature(parameters: &Parameters) -> Vec<&Expr> {
    parameters
        .iter()
        .flat_map(|parameter| {
            parameter
                .annotation()
                .into_iter()
                .chain(parameter.default())
        })
        .collect()
}

fn bounds(parameters: &ruff_python_ast::TypeParams) -> Vec<&Expr> {
    parameters
        .iter()
        .flat_map(|parameter| match parameter {
            ruff_python_ast::TypeParam::TypeVar(item) => item
                .bound
                .iter()
                .chain(item.default.iter())
                .map(AsRef::as_ref)
                .collect::<Vec<_>>(),
            ruff_python_ast::TypeParam::ParamSpec(item) => {
                item.default.iter().map(AsRef::as_ref).collect()
            }
            ruff_python_ast::TypeParam::TypeVarTuple(item) => {
                item.default.iter().map(AsRef::as_ref).collect()
            }
        })
        .collect()
}

fn type_parameters(statement: &Stmt) -> Vec<&Expr> {
    match statement {
        Stmt::FunctionDef(item) => item
            .type_params
            .iter()
            .flat_map(|params| bounds(params))
            .collect(),
        Stmt::ClassDef(item) => item
            .type_params
            .iter()
            .flat_map(|params| bounds(params))
            .collect(),
        Stmt::TypeAlias(item) => item
            .type_params
            .iter()
            .flat_map(|params| bounds(params))
            .collect(),
        _ => Vec::new(),
    }
}
