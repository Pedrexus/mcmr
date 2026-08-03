use crate::graph::construction::{identity, node};
use crate::graph::contracts::{Edge, EdgeKind, Language, Node, NodeKind, Reference, Resolution};
use crate::graph::resolution_engine::attachment::Attachment;
use std::collections::{BTreeMap, BTreeSet};

/// Attach one reference to the first candidate the repository declares.
pub(crate) fn attach(
    attachment: Attachment<'_>,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) -> bool {
    let Some(qualname) = attachment
        .candidates
        .iter()
        .find(|candidate| !candidate.is_empty() && attachment.symbols.contains(*candidate))
    else {
        return false;
    };
    let kind = target_kind(attachment.reference.language, qualname, nodes);
    let relation = match (attachment.relation_kind, kind) {
        (EdgeKind::Call, NodeKind::Class) => EdgeKind::Instantiate,
        (kind, _) => kind,
    };
    edges.push(attached_edge(&attachment, kind, qualname, relation));
    true
}

fn attached_edge(
    attachment: &Attachment<'_>,
    kind: NodeKind,
    qualname: &str,
    relation: EdgeKind,
) -> Edge {
    Edge {
        source: attachment.reference.source.clone(),
        target: identity(attachment.reference.language, kind, qualname),
        kind: relation,
        path: attachment.reference.location.path.clone(),
        line: attachment.reference.location.line,
        resolution: Resolution::Exact,
    }
}

/// Attach one reference to a placeholder for the declaration this repository does not hold.
///
/// A name that leaves the repository and a name nothing here explains are both worth keeping. The
/// first is a dependency and the second is a gap in this kernel, and an edge that states which one
/// it is lets a reader tell them apart instead of trusting a silence.
pub fn stray(
    reference: &Reference,
    kind: NodeKind,
    qualname: &str,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let placeholder = node(reference.language, kind, qualname);
    let target = placeholder.id.clone();
    nodes.entry(target.clone()).or_insert(placeholder);
    edges.push(Edge {
        source: reference.source.clone(),
        target,
        kind: reference.kind,
        path: reference.location.path.clone(),
        line: reference.location.line,
        resolution: if kind == NodeKind::UnresolvedSymbol {
            Resolution::Unresolved
        } else {
            Resolution::External
        },
    });
}

/// Return the module that defines a reexported symbol.
pub(super) fn through_reexport(
    expression: &str,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    modules: &BTreeSet<String>,
) -> Option<String> {
    let mut current = expression;
    let mut visited = BTreeSet::new();
    while visited.insert(current) {
        let (_, symbol) = current.rsplit_once('.')?;
        let (bound, defining) = reexport_step(current, aliases, modules)?;
        if !aliases
            .get(defining)
            .is_some_and(|held| held.contains_key(symbol))
        {
            return Some(defining.to_string());
        }
        current = bound;
    }
    None
}

fn reexport_step<'a>(
    current: &'a str,
    aliases: &'a BTreeMap<String, BTreeMap<String, String>>,
    modules: &BTreeSet<String>,
) -> Option<(&'a str, &'a str)> {
    let (holder, symbol) = current.rsplit_once('.')?;
    let bound = aliases.get(holder)?.get(symbol)?;
    let (defining, _) = bound.rsplit_once('.')?;
    (modules.contains(holder) && defining != holder && modules.contains(defining))
        .then_some((bound, defining))
}

/// Return the expression with its leading name replaced by whatever it was imported as.
pub fn expand(expression: &str, aliases: &BTreeMap<String, String>) -> String {
    let (head, rest) = expression.split_once('.').unwrap_or((expression, ""));
    match aliases.get(head) {
        Some(target) if rest.is_empty() => target.clone(),
        Some(target) => format!("{target}.{rest}"),
        None => expression.to_string(),
    }
}

/// Whether one expression is a plain dotted name rather than something with syntax in it.
pub(super) fn is_dotted_path(expression: &str) -> bool {
    !expression.is_empty()
        && expression.split('.').all(|part| {
            !part.is_empty()
                && part
                    .chars()
                    .next()
                    .is_some_and(|first| first.is_alphabetic() || first == '_')
                && part
                    .chars()
                    .all(|letter| letter.is_alphanumeric() || letter == '_')
        })
}

/// Whether one bare name is a Python builtin, which the oracle treats as external.
const PYTHON_BUILTINS: &[&str] = &[
    "abs",
    "all",
    "any",
    "bool",
    "bytes",
    "callable",
    "classmethod",
    "dict",
    "dir",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "hasattr",
    "hash",
    "id",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "open",
    "ord",
    "print",
    "property",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "setattr",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "super",
    "tuple",
    "type",
    "vars",
    "zip",
    "Exception",
    "ValueError",
    "TypeError",
    "KeyError",
    "RuntimeError",
    "NotImplementedError",
    "AttributeError",
    "IndexError",
    "StopIteration",
    "OSError",
    "SystemExit",
    "KeyboardInterrupt",
    "GeneratorExit",
    "BaseException",
    "BaseExceptionGroup",
    "ExceptionGroup",
    "LookupError",
    "ImportError",
    "ModuleNotFoundError",
    "MemoryError",
    "NameError",
    "OverflowError",
    "RecursionError",
    "ReferenceError",
    "StopAsyncIteration",
    "SyntaxError",
    "SystemError",
    "UnicodeError",
    "ZeroDivisionError",
    "ArithmeticError",
    "AssertionError",
    "BufferError",
    "EOFError",
    "FileNotFoundError",
    "FloatingPointError",
    "PermissionError",
    "TimeoutError",
    "UnboundLocalError",
    "Warning",
    "bytearray",
    "complex",
    "compile",
    "delattr",
    "divmod",
    "eval",
    "exec",
    "globals",
    "hex",
    "input",
    "locals",
    "memoryview",
    "oct",
    "pow",
    "aiter",
    "anext",
    "ascii",
    "bin",
    "breakpoint",
    "chr",
    "help",
    "issubclass",
    "iter",
    "license",
    "NotImplemented",
    "Ellipsis",
    "None",
    "True",
    "False",
];

pub(crate) fn is_builtin(name: &str) -> bool {
    PYTHON_BUILTINS.contains(&name)
}

fn target_kind(language: Language, qualname: &str, nodes: &BTreeMap<String, Node>) -> NodeKind {
    for kind in [
        NodeKind::Class,
        NodeKind::Function,
        NodeKind::Method,
        NodeKind::Property,
        NodeKind::Module,
        NodeKind::Variable,
        NodeKind::Attribute,
    ] {
        if nodes.contains_key(&identity(language, kind, qualname)) {
            return kind;
        }
    }
    NodeKind::UnresolvedSymbol
}
