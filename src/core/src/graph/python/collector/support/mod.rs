use crate::graph::contracts::{ParameterKind, Visibility};
use crate::walk::qualified_name;
use ruff_python_ast::{AnyParameterRef, Expr, Parameters, Stmt};

/// Return one rendered expression with plain double-quoted strings restated in single quotes.
///
/// The oracle prints through the Python unparser, which always chooses a single quote. Matching
/// that keeps two producers naming the same unresolved expression identically.
pub(super) fn normalize_quotes(text: &str) -> String {
    if text.contains('\'') {
        return text.to_string();
    }
    text.replace('"', "'")
}

/// Return every parameter one Python signature states, each beside the way it binds.
///
/// Python separates the five kinds in its own grammar, so every answer here is read rather than
/// inferred, down to the two variadic forms that the grammar itself forbids a default on. The
/// order is the one a reader meets in the source, which is what makes the ordinal a position.
pub(super) fn python_parameters(stated: &Parameters) -> Vec<(AnyParameterRef<'_>, ParameterKind)> {
    let positional_only = stated.posonlyargs.iter().map(|item| {
        (
            AnyParameterRef::NonVariadic(item),
            ParameterKind::PositionalOnly,
        )
    });
    let positional_or_keyword = stated.args.iter().map(|item| {
        (
            AnyParameterRef::NonVariadic(item),
            ParameterKind::PositionalOrKeyword,
        )
    });
    let var_positional = stated.vararg.as_deref().map(|item| {
        (
            AnyParameterRef::Variadic(item),
            ParameterKind::VarPositional,
        )
    });
    let keyword_only = stated.kwonlyargs.iter().map(|item| {
        (
            AnyParameterRef::NonVariadic(item),
            ParameterKind::KeywordOnly,
        )
    });
    let var_keyword = stated
        .kwarg
        .as_deref()
        .map(|item| (AnyParameterRef::Variadic(item), ParameterKind::VarKeyword));
    positional_only
        .chain(positional_or_keyword)
        .chain(var_positional)
        .chain(keyword_only)
        .chain(var_keyword)
        .collect()
}

/// Return one expression as a dotted name, when every step of it is a plain name.
pub(super) fn dotted(expression: &Expr) -> Option<String> {
    match expression {
        Expr::Name(name) => Some(name.id.to_string()),
        Expr::Attribute(item) => Some(format!("{}.{}", dotted(&item.value)?, item.attr)),
        _ => None,
    }
}

/// Return every name one annotation states, unwrapping the containers that hold them.
///
/// `Mapping[str, Fact]` depends on three names, not on one, so a subscript is opened rather than
/// read as a single type. A string annotation is a forward reference and states its name plainly.
pub(super) fn annotation_names(annotation: &Expr) -> Vec<String> {
    match annotation {
        Expr::Name(name) => vec![name.id.to_string()],
        Expr::Attribute(_) => vec![qualified_name(annotation)],
        Expr::StringLiteral(literal) => vec![literal.value.to_str().to_string()],
        Expr::Subscript(item) => {
            let mut names = annotation_names(&item.value);
            names.extend(annotation_names(&item.slice));
            names
        }
        Expr::Tuple(item) => item.elts.iter().flat_map(annotation_names).collect(),
        Expr::BinOp(item) => {
            let mut names = annotation_names(&item.left);
            names.extend(annotation_names(&item.right));
            names
        }
        _ => Vec::new(),
    }
}

pub(super) fn tail(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}

pub(super) fn is_type_checking(test: &Expr) -> bool {
    match test {
        Expr::Name(name) => name.id.as_str() == "TYPE_CHECKING",
        Expr::Attribute(item) => item.attr.as_str() == "TYPE_CHECKING",
        _ => false,
    }
}

/// Whether one Python class states a contract rather than implementing one.
///
/// Python spells this three ways and all three are here. Deriving `ABC` or naming `ABCMeta` as the
/// metaclass says the class refuses to be instantiated, deriving `Protocol` says it exists to be
/// matched structurally and never constructed, and declaring a member the subclass has to write is
/// the same statement made one method at a time.
///
/// It stays deliberately local. A subclass of an abstract class is usually the concrete half of
/// the pair, so following the inheritance chain would read every implementation as an interface,
/// which is the opposite of what the measure is for.
pub(super) fn is_contract(item: &ruff_python_ast::StmtClassDef) -> bool {
    const CONTRACTS: &[&str] = &["ABC", "ABCMeta", "Protocol"];
    let arguments = item.arguments.iter().flat_map(|stated| {
        stated
            .args
            .iter()
            .chain(stated.keywords.iter().map(|keyword| &keyword.value))
    });
    arguments
        .map(qualified_name)
        .any(|named| CONTRACTS.contains(&tail(&named)))
        || item.body.iter().any(|member| match member {
            Stmt::FunctionDef(callable) => callable.decorator_list.iter().any(|decorator| {
                tail(&qualified_name(&decorator.expression)).starts_with("abstract")
            }),
            _ => false,
        })
}

/// Return the visibility one Python name states, since this language states it in the name.
pub(super) fn python_visibility(name: &str) -> Visibility {
    if name.starts_with("__") && name.ends_with("__") {
        Visibility::Public
    } else if name.starts_with("__") {
        Visibility::Private
    } else if name.starts_with('_') {
        Visibility::Internal
    } else {
        Visibility::Public
    }
}
