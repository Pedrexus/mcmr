use ruff_python_ast::{Expr, ModModule, Parameters, Stmt};
use ruff_text_size::Ranged;

/// Return every statement in the module, including nested ones.
pub fn walk(module: &ModModule) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = module.body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Return the statement blocks one statement owns.
pub fn blocks(statement: &Stmt) -> Vec<&[Stmt]> {
    match statement {
        Stmt::FunctionDef(item) => vec![&item.body],
        Stmt::ClassDef(item) => vec![&item.body],
        Stmt::If(item) => {
            let mut blocks: Vec<&[Stmt]> = vec![&item.body];
            blocks.extend(
                item.elif_else_clauses
                    .iter()
                    .map(|clause| clause.body.as_slice()),
            );
            blocks
        }
        Stmt::For(item) => vec![&item.body, &item.orelse],
        Stmt::While(item) => vec![&item.body, &item.orelse],
        Stmt::With(item) => vec![&item.body],
        // A handler is a block like any other. Leaving it out made a guard look as though it
        // held only the region it protects, so nothing could read what a project does when a
        // failure actually arrives.
        Stmt::Try(item) => {
            let mut blocks: Vec<&[Stmt]> = vec![&item.body];
            blocks.extend(item.handlers.iter().map(|clause| match clause {
                ruff_python_ast::ExceptHandler::ExceptHandler(held) => held.body.as_slice(),
            }));
            blocks.extend([item.orelse.as_slice(), item.finalbody.as_slice()]);
            blocks
        }
        Stmt::Match(item) => item.cases.iter().map(|case| case.body.as_slice()).collect(),
        _ => Vec::new(),
    }
}

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
        Stmt::TypeAlias(item) => vec![item.value.as_ref()],
        Stmt::FunctionDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .chain(item.returns.iter().map(AsRef::as_ref))
            .chain(signature(&item.parameters))
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
        Expr::ListComp(item) => {
            let mut inner = vec![item.elt.as_ref()];
            inner.extend(clauses(&item.generators));
            inner
        }
        Expr::SetComp(item) => {
            let mut inner = vec![item.elt.as_ref()];
            inner.extend(clauses(&item.generators));
            inner
        }
        Expr::Generator(item) => {
            let mut inner = vec![item.elt.as_ref()];
            inner.extend(clauses(&item.generators));
            inner
        }
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
        // An interpolated string evaluates every expression it holds, so a call written inside one
        // is a call like any other.
        Expr::FString(item) => item
            .value
            .elements()
            .filter_map(|element| element.as_interpolation())
            .map(|interpolation| interpolation.expression.as_ref())
            .collect(),
        _ => Vec::new(),
    }
}

/// Return every clause expression one comprehension iterates and filters on.
pub fn clauses(generators: &[ruff_python_ast::Comprehension]) -> Vec<&Expr> {
    generators
        .iter()
        .flat_map(|generator| std::iter::once(&generator.iter).chain(generator.ifs.iter()))
        .collect()
}

/// Return the annotations and defaults one parameter list declares.
pub fn signature(parameters: &Parameters) -> Vec<&Expr> {
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

/// Return the bounds and defaults one type parameter list declares.
pub fn bounds(parameters: &ruff_python_ast::TypeParams) -> Vec<&Expr> {
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

/// Return the type parameters one statement declares, when it declares any.
pub fn type_parameters(statement: &Stmt) -> Vec<&Expr> {
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

pub fn qualified_name(expression: &Expr) -> String {
    match expression {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => {
            let base = qualified_name(&attribute.value);
            if base.is_empty() {
                String::new()
            } else {
                format!("{base}.{}", attribute.attr)
            }
        }
        Expr::Call(call) => qualified_name(&call.func),
        _ => String::new(),
    }
}

pub fn annotation_name(annotation: &Expr) -> String {
    match annotation {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => attribute.attr.to_string(),
        Expr::StringLiteral(literal) => literal.value.to_str().to_string(),
        Expr::Subscript(subscript) => annotation_name(&subscript.value),
        _ => String::new(),
    }
}

pub fn docstring(body: &[Stmt]) -> Option<String> {
    match body.first() {
        Some(Stmt::Expr(item)) => match item.value.as_ref() {
            Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
            _ => None,
        },
        _ => None,
    }
}

/// Return the range one statement block covers, from its first statement to its last.
pub fn body_range(body: &[Stmt]) -> ruff_text_size::TextRange {
    match (body.first(), body.last()) {
        (Some(first), Some(last)) => {
            ruff_text_size::TextRange::new(first.range().start(), last.range().end())
        }
        _ => ruff_text_size::TextRange::default(),
    }
}

pub fn declared_name(statement: &Stmt) -> Option<String> {
    match statement {
        Stmt::ClassDef(item) => Some(item.name.to_string()),
        Stmt::FunctionDef(item) => Some(item.name.to_string()),
        _ => None,
    }
}
