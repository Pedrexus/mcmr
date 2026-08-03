use crate::graph::contracts::{
    Edge, EdgeKind, Language, Node, NodeKind, ParameterKind, Resolution, Visibility,
};

/// Identify one symbol by the namespace of the language that declared it.
pub fn identity(language: Language, kind: NodeKind, qualname: &str) -> String {
    format!(
        "{}:{}:{qualname}",
        language.namespace().label(),
        kind.label()
    )
}

/// Declare one symbol, which some language wrote and some language names.
pub fn node(language: Language, kind: NodeKind, qualname: &str) -> Node {
    Node::new(
        identity(language, kind, qualname),
        kind,
        Some(language),
        Visibility::Public,
        qualname.to_string(),
    )
}

/// Declare one parameter, which the frontend that reads its calling convention must classify.
///
/// A parameter cannot be minted without saying how it binds, because a rule comparing two
/// signatures has no way to guess and every frontend here knows the answer from its own grammar.
pub fn parameter(language: Language, qualname: &str, ordinal: usize, kind: ParameterKind) -> Node {
    let mut declared = node(language, NodeKind::Parameter, qualname);
    declared.ordinal = Some(ordinal);
    declared.parameter_kind = Some(kind);
    declared
}

pub(crate) struct ExactEdge<'a> {
    pub(crate) source: &'a str,
    pub(crate) target: &'a str,
    pub(crate) kind: EdgeKind,
    pub(crate) path: &'a str,
    pub(crate) line: usize,
}

pub(crate) fn relate(edges: &mut Vec<Edge>, relation: ExactEdge<'_>) {
    edges.push(Edge {
        source: relation.source.to_string(),
        target: relation.target.to_string(),
        kind: relation.kind,
        path: relation.path.to_string(),
        line: relation.line,
        resolution: Resolution::Exact,
    });
}
