use serde::Serialize;

/// What one node in the repository graph is.
///
/// The vocabulary matches the Archy oracle exactly, because the graph is only useful if two
/// producers name the same entity the same way. A symbol is identified as
/// `{language}:{kind}:{qualname}` and a path entity as `path:{kind}:{path}`, so a node survives an
/// edit that moves it and two runs over unchanged source agree.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum NodeKind {
    Repository,
    Directory,
    File,
    Module,
    Class,
    Function,
    Method,
    Property,
    Attribute,
    Variable,
    Parameter,
    ExternalModule,
    ExternalSymbol,
    UnresolvedSymbol,
}

impl NodeKind {
    /// Whether one node is a place on disk rather than something a language declared.
    ///
    /// A directory holding Python beside Rust belongs to neither, so a path entity is named by its
    /// path alone and every frontend that walks into it finds the same node already there.
    pub(crate) fn is_path_entity(self) -> bool {
        matches!(
            self,
            NodeKind::Repository | NodeKind::Directory | NodeKind::File
        )
    }

    pub(crate) fn label(self) -> &'static str {
        match self {
            NodeKind::Repository => "repository",
            NodeKind::Directory => "directory",
            NodeKind::File => "file",
            NodeKind::Module => "module",
            NodeKind::Class => "class",
            NodeKind::Function => "function",
            NodeKind::Method => "method",
            NodeKind::Property => "property",
            NodeKind::Attribute => "attribute",
            NodeKind::Variable => "variable",
            NodeKind::Parameter => "parameter",
            NodeKind::ExternalModule => "external-module",
            NodeKind::ExternalSymbol => "external-symbol",
            NodeKind::UnresolvedSymbol => "unresolved-symbol",
        }
    }
}
