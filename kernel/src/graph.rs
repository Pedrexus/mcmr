use crate::discovery::{Crates, Document, Packages};
use crate::source::Source;
use crate::walk::{annotation_name, qualified_name};
use ruff_python_ast::{AnyParameterRef, Expr, ModModule, Parameters, Stmt};
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// Which language declared one symbol, which its identity carries.
///
/// A monorepo names the same thing twice. A `kernel::graph::build` written in Rust and a
/// `mcmr.engine.build` written in Python are different symbols that a shared graph has to keep
/// apart, so the language leads every identity a frontend mints.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Language {
    Python,
    Rust,
    TypeScript,
    C,
    Cpp,
    Cuda,
}

impl Language {
    /// Return the language one path is written in, when this kernel has a frontend for it.
    pub fn of(path: &str) -> Option<Self> {
        match path.rsplit('.').next().unwrap_or_default() {
            "py" | "pyi" => Some(Language::Python),
            "rs" => Some(Language::Rust),
            "ts" | "tsx" | "mts" | "cts" => Some(Language::TypeScript),
            "cu" | "cuh" => Some(Language::Cuda),
            "cpp" | "cc" | "cxx" | "hpp" | "hh" => Some(Language::Cpp),
            "c" | "h" => Some(Language::C),
            _ => None,
        }
    }

    fn label(self) -> &'static str {
        match self {
            Language::Python => "python",
            Language::Rust => "rust",
            Language::TypeScript => "typescript",
            Language::C => "c",
            Language::Cpp => "cpp",
            Language::Cuda => "cuda",
        }
    }

    /// Return what this language writes between a holder and the name it holds.
    pub fn separator(self) -> &'static str {
        match self {
            Language::Python | Language::TypeScript => ".",
            Language::Rust | Language::C | Language::Cpp | Language::Cuda => "::",
        }
    }

    /// Return the language whose namespace this one shares.
    ///
    /// A header, a translation unit, and a CUDA source name each other directly and link into one
    /// program, so a class declared in a header and defined in a `.cpp` is one class rather than
    /// two. Every other language here keeps its own namespace.
    fn namespace(self) -> Self {
        match self {
            Language::C | Language::Cuda => Language::Cpp,
            other => other,
        }
    }
}

/// How widely one declaration reaches, in the one vocabulary every frontend fills.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Visibility {
    Public,
    Protected,
    Internal,
    Private,
}

/// How one parameter binds the argument a caller passes to it.
///
/// Python is the language that spells all five, and the vocabulary is written from it because
/// naming a distinction is the only way another frontend can say it does not have one. Rust, C,
/// C++, and CUDA bind every named argument by position and offer no keyword at all, so their
/// parameters are positional-only and nothing about that is an approximation. What separates a
/// position a caller must fill from a name a caller may pass is exactly what tells an override
/// that broke its callers from one that merely reads differently.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ParameterKind {
    PositionalOnly,
    PositionalOrKeyword,
    KeywordOnly,
    VarPositional,
    VarKeyword,
}

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
    fn label(self) -> &'static str {
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

    /// Whether one node is a place on disk rather than something a language declared.
    ///
    /// A directory holding Python beside Rust belongs to neither, so a path entity is named by its
    /// path alone and every frontend that walks into it finds the same node already there.
    fn is_path_entity(self) -> bool {
        matches!(
            self,
            NodeKind::Repository | NodeKind::Directory | NodeKind::File
        )
    }
}

/// What one relationship between two nodes is.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum EdgeKind {
    Contain,
    Define,
    Import,
    Call,
    Instantiate,
    Inherit,
    Typed,
    Access,
}

/// How completely one relationship was resolved, which a consumer must be able to see.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Resolution {
    Exact,
    External,
    Unresolved,
}

#[derive(Clone, Debug, Serialize)]
pub struct Node {
    pub id: String,
    pub kind: NodeKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language: Option<Language>,
    pub visibility: Visibility,
    pub qualname: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub is_package: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotation: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub return_annotation: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub decorators: Vec<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub asynchronous: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ordinal: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parameter_kind: Option<ParameterKind>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub has_default: bool,
    /// Whether this declaration states a contract rather than an implementation of one.
    ///
    /// Every language spells the same idea differently and each frontend answers for its own:
    /// a Python class deriving `ABC` or `Protocol` or holding an `@abstractmethod`, a Rust
    /// trait, and a C++ type declaring a pure virtual. Nothing above the frontend guesses,
    /// because a guess would read a plain struct as an interface in whichever language the
    /// reader knows least.
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub is_abstract: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Edge {
    pub source: String,
    pub target: String,
    pub kind: EdgeKind,
    pub path: String,
    pub line: usize,
    pub resolution: Resolution,
}

/// The repository graph, with its nodes and every source site that relates them.
#[derive(Debug, Default, Serialize)]
pub struct Graph {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

/// One reference awaiting the repository-wide resolution its own module cannot perform.
pub struct Reference {
    pub source: String,
    pub expression: String,
    pub language: Language,
    pub module: String,
    pub owner: Option<String>,
    pub receiver_type: Option<String>,
    pub kind: EdgeKind,
    pub path: String,
    pub line: usize,
}

/// Build the whole repository graph from documents that were already read.
///
/// One naming pass decides what every file calls itself, one frontend pass per language states the
/// definitions and the references each file makes, and one resolution pass attaches every reference
/// to the declaration it named. A language reaches the graph by adding a frontend to the middle
/// pass, which is why the ends of this function say nothing about any particular language.
pub fn build(root: &str, documents: &[Document]) -> Graph {
    let naming = Naming::of(documents);
    let specifiers = crate::typescript::Specifiers::of(root, naming.typescript(documents));
    let mut nodes: BTreeMap<String, Node> = BTreeMap::new();
    let mut edges: Vec<Edge> = Vec::new();
    let mut placed: BTreeSet<(String, String)> = BTreeSet::new();
    let mut references: Vec<Reference> = Vec::new();
    workspace(
        root,
        documents,
        &naming,
        &mut nodes,
        &mut edges,
        &mut placed,
    );
    let mut aliases: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    for document in documents {
        let Some((language, module)) = naming.module(&document.relative) else {
            continue;
        };
        let source = Source::new(&document.relative, &document.source);
        let stated = match language {
            Language::Python => python(source, &module),
            Language::Rust => crate::rust::graph(source, &module),
            Language::TypeScript => crate::typescript::graph(source, &module, &specifiers),
            native => crate::native::graph(source, &module, native),
        };
        let Some(mut stated) = stated else { continue };
        aliases.insert(module, stated.aliases);
        nodes.extend(stated.nodes.into_iter().map(|node| (node.id.clone(), node)));
        edges.append(&mut stated.edges);
        references.append(&mut stated.references);
    }
    let symbols: BTreeSet<String> = nodes
        .values()
        .filter(|node| !node.kind.is_path_entity() && node.kind != NodeKind::Parameter)
        .map(|node| node.qualname.clone())
        .collect();
    let modules: BTreeSet<String> = nodes
        .values()
        .filter(|node| node.kind == NodeKind::Module)
        .map(|node| node.qualname.clone())
        .collect();
    let lookup = crate::native::Lookup::of(&symbols);
    for reference in references {
        let reachable = if reference.kind == EdgeKind::Import {
            &modules
        } else {
            &symbols
        };
        match reference.language {
            Language::Rust => {
                crate::rust::resolve(&reference, reachable, &aliases, &mut nodes, &mut edges);
            }
            Language::C | Language::Cpp | Language::Cuda => {
                crate::native::resolve(&reference, reachable, &lookup, &mut nodes, &mut edges);
            }
            Language::TypeScript => {
                crate::typescript::resolve(
                    &reference, &modules, &symbols, &aliases, &mut nodes, &mut edges,
                );
            }
            _ => resolve(&reference, reachable, &aliases, &mut nodes, &mut edges),
        }
    }
    Graph {
        nodes: nodes.into_values().collect(),
        edges,
    }
}

/// Everything one file states about itself, which resolution then joins to the repository.
#[derive(Default)]
pub struct Stated {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub references: Vec<Reference>,
    pub aliases: BTreeMap<String, String>,
}

fn python(source: Source, module: &str) -> Option<Stated> {
    let parsed = parse_module(&source.text).ok()?;
    let mut collector = Collector::new(source, module.to_string());
    collector.module(parsed.syntax());
    Some(Stated {
        nodes: collector.nodes,
        edges: collector.edges,
        references: collector.references,
        aliases: collector.aliases,
    })
}

/// What every file in the repository calls itself, in the naming rule of its own language.
struct Naming {
    packages: Packages,
    crates: Crates,
}

impl Naming {
    fn of(documents: &[Document]) -> Self {
        Self {
            packages: Packages::of(documents),
            crates: Crates::of(documents),
        }
    }

    /// Return the language one file is written in and the module name that language gives it.
    ///
    /// A native translation unit has no import system to ask, so its path is its name, minus the
    /// suffix that says which half of the pair it is. That is what puts a header and the unit
    /// implementing it into one module, which is where they already belong.
    ///
    /// TypeScript names a module by its path too, and keeps the separator that path is written
    /// with. Every specifier it resolves is a path, so a name that reads back as one is the name
    /// resolution already has to compute, and two files never collapse onto one module the way
    /// they would if the suffix decided.
    fn module(&self, relative: &str) -> Option<(Language, String)> {
        let language = Language::of(relative)?;
        let stem = relative
            .rsplit_once('.')
            .map(|(stem, _)| stem)
            .unwrap_or(relative);
        let module = match language {
            Language::Python => self.packages.module_name(relative),
            Language::Rust => self.crates.module_name(relative),
            Language::TypeScript => stem.to_string(),
            _ => stem.replace('/', "::"),
        };
        Some((language, module))
    }

    /// Return every module the TypeScript files of this repository declare.
    ///
    /// Resolution in this language is a question about which paths exist, since `./thing` reaches
    /// `thing.ts`, `thing.d.ts`, or `thing/index.ts` and only the repository says which. Handing
    /// the frontend the whole set is what lets it answer that without walking the disk again.
    fn typescript(&self, documents: &[Document]) -> BTreeSet<String> {
        documents
            .iter()
            .filter_map(|document| match self.module(&document.relative) {
                Some((Language::TypeScript, module)) => Some(module),
                _ => None,
            })
            .collect()
    }
}

/// Return the module one `from` import names, resolved against the module that states it.
///
/// A relative import is written against the package the importing module sits in, so the same
/// line means a different module in every file, and nothing downstream can compare a definition to
/// its consumers until that is settled. The package of a module is itself when the module is a
/// package initializer and its parent otherwise, which is the one distinction the dots count from.
pub fn absolute_module(
    module: &str,
    is_package: bool,
    item: &ruff_python_ast::StmtImportFrom,
) -> String {
    let target = item
        .module
        .as_ref()
        .map(ToString::to_string)
        .unwrap_or_default();
    if item.level == 0 {
        return target;
    }
    let mut parts: Vec<&str> = module.split('.').collect();
    if !is_package {
        parts.pop();
    }
    let kept = (parts.len() + 1).saturating_sub(item.level as usize);
    let package = parts[..kept.min(parts.len())].join(".");
    match (package.is_empty(), target.is_empty()) {
        (true, _) => target,
        (false, true) => package,
        (false, false) => format!("{package}.{target}"),
    }
}

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
    Node {
        id: identity(language, kind, qualname),
        kind,
        language: Some(language),
        visibility: Visibility::Public,
        qualname: qualname.to_string(),
        path: None,
        is_package: false,
        line: None,
        annotation: None,
        return_annotation: None,
        decorators: Vec::new(),
        asynchronous: false,
        ordinal: None,
        parameter_kind: None,
        has_default: false,
        is_abstract: false,
    }
}

/// Declare one parameter, which the frontend that reads its calling convention must classify.
///
/// A parameter cannot be minted without saying how it binds, because a rule comparing two
/// signatures has no way to guess and every frontend here knows the answer from its own grammar.
pub fn parameter(
    language: Language,
    qualname: &str,
    ordinal: usize,
    kind: ParameterKind,
    has_default: bool,
) -> Node {
    Node {
        ordinal: Some(ordinal),
        parameter_kind: Some(kind),
        has_default,
        ..node(language, NodeKind::Parameter, qualname)
    }
}

/// Place one path entity, which is somewhere on disk rather than something a language declared.
fn place(kind: NodeKind, path: &str) -> Node {
    Node {
        id: format!("path:{}:{path}", kind.label()),
        kind,
        language: None,
        visibility: Visibility::Public,
        qualname: path.to_string(),
        path: None,
        is_package: false,
        line: None,
        annotation: None,
        return_annotation: None,
        decorators: Vec::new(),
        asynchronous: false,
        ordinal: None,
        parameter_kind: None,
        has_default: false,
        is_abstract: false,
    }
}

/// Place the repository, its directories, its files, and the modules they hold.
fn workspace(
    root: &str,
    documents: &[Document],
    naming: &Naming,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
    placed: &mut BTreeSet<(String, String)>,
) {
    let name = root
        .trim_end_matches('/')
        .rsplit('/')
        .next()
        .unwrap_or(root);
    let repository = place(NodeKind::Repository, name);
    let repository_id = repository.id.clone();
    nodes.insert(repository_id.clone(), repository);
    for document in documents {
        let mut owner = repository_id.clone();
        let parts: Vec<&str> = document.relative.split('/').collect();
        for depth in 1..parts.len() {
            let directory = parts[..depth].join("/");
            let entry = place(NodeKind::Directory, &directory);
            let id = entry.id.clone();
            nodes.entry(id.clone()).or_insert(entry);
            if placed.insert((owner.clone(), id.clone())) {
                relate(edges, &owner, &id, EdgeKind::Contain, &document.relative, 1);
            }
            owner = id;
        }
        let mut file = place(NodeKind::File, &document.relative);
        file.path = Some(document.relative.clone());
        file.language = Language::of(&document.relative);
        let file_id = file.id.clone();
        nodes.entry(file_id.clone()).or_insert(file);
        if placed.insert((owner.clone(), file_id.clone())) {
            relate(
                edges,
                &owner,
                &file_id,
                EdgeKind::Contain,
                &document.relative,
                1,
            );
        }
        let Some((language, named)) = naming.module(&document.relative) else {
            continue;
        };
        let mut module = node(language, NodeKind::Module, &named);
        module.path = Some(document.relative.clone());
        module.is_package = document.relative.ends_with("__init__.py")
            || document.relative.ends_with("/mod.rs")
            || document.relative.ends_with("/lib.rs")
            || document.relative.ends_with("/index.ts")
            || document.relative.ends_with("/index.tsx");
        let module_id = module.id.clone();
        nodes.entry(module_id.clone()).or_insert(module);
        relate(
            edges,
            &file_id,
            &module_id,
            EdgeKind::Define,
            &document.relative,
            1,
        );
    }
}

fn relate(
    edges: &mut Vec<Edge>,
    source: &str,
    target: &str,
    kind: EdgeKind,
    path: &str,
    line: usize,
) {
    edges.push(Edge {
        source: source.to_string(),
        target: target.to_string(),
        kind,
        path: path.to_string(),
        line,
        resolution: Resolution::Exact,
    });
}

/// Collect every definition and reference one module states.
struct Collector {
    source: Source,
    module: String,
    is_package: bool,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    references: Vec<Reference>,
    aliases: BTreeMap<String, String>,
    owners: Vec<(String, NodeKind, String)>,
    classes: Vec<String>,
    types: Vec<BTreeMap<String, String>>,
}

impl Collector {
    fn new(source: Source, module: String) -> Self {
        let owner = (
            identity(Language::Python, NodeKind::Module, &module),
            NodeKind::Module,
            module.clone(),
        );
        Self {
            is_package: source.relative.ends_with("__init__.py"),
            source,
            module,
            nodes: Vec::new(),
            edges: Vec::new(),
            references: Vec::new(),
            aliases: BTreeMap::new(),
            owners: vec![owner],
            classes: Vec::new(),
            types: vec![BTreeMap::new()],
        }
    }

    fn module(&mut self, module: &ModModule) {
        self.body(&module.body);
    }

    fn body(&mut self, body: &[Stmt]) {
        for statement in body {
            self.statement(statement);
        }
    }

    fn statement(&mut self, statement: &Stmt) {
        match statement {
            Stmt::ClassDef(item) => self.class(statement, item),
            Stmt::FunctionDef(item) => self.callable(statement, item),
            Stmt::Assign(item) => {
                for target in &item.targets {
                    self.assignment(statement, target, None);
                }
                self.expression(&item.value);
            }
            Stmt::AnnAssign(item) => {
                if let Expr::Name(name) = item.target.as_ref() {
                    self.declare(name.id.as_str(), Some(annotation_name(&item.annotation)));
                }
                let owner = self.owners.last().unwrap().0.clone();
                self.annotation(&owner, &item.annotation);
                self.assignment(
                    statement,
                    &item.target,
                    Some(annotation_name(&item.annotation)),
                );
                if let Some(value) = &item.value {
                    self.expression(value);
                }
            }
            Stmt::Import(item) => {
                for alias in &item.names {
                    let bound = alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| alias.name.to_string());
                    self.aliases.insert(bound, alias.name.to_string());
                    self.import(alias.name.as_ref(), statement);
                }
            }
            Stmt::ImportFrom(item) => {
                let target = absolute_module(&self.module, self.is_package, item);
                for alias in &item.names {
                    let bound = alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| alias.name.to_string());
                    let imported = format!("{target}.{}", alias.name);
                    self.aliases.insert(bound, imported.clone());
                    self.import(&imported, statement);
                    // The import edge names the module it resolved to. A package initializer that
                    // re-exports a symbol reaches that symbol, and nothing else records it.
                    let owner = identity(Language::Python, NodeKind::Module, &self.module);
                    self.reference(
                        &owner,
                        &imported,
                        EdgeKind::Access,
                        statement.range().start(),
                    );
                }
            }
            // A branch guarded by `TYPE_CHECKING` never runs, so nothing inside it belongs to the
            // runtime structure. Its else branch does.
            Stmt::If(item) if is_type_checking(&item.test) => {
                for clause in &item.elif_else_clauses {
                    self.body(&clause.body);
                }
            }
            _ => {
                for expression in crate::walk::expressions(statement) {
                    self.expression(expression);
                }
                for block in crate::walk::blocks(statement) {
                    self.body(block);
                }
            }
        }
    }

    fn import(&mut self, target: &str, statement: &Stmt) {
        self.references.push(Reference {
            language: Language::Python,
            source: identity(Language::Python, NodeKind::Module, &self.module),
            expression: target.to_string(),
            module: self.module.clone(),
            owner: None,
            receiver_type: None,
            kind: EdgeKind::Import,
            path: self.source.relative.clone(),
            line: self.source.line_of(statement.range().start()),
        });
    }

    fn class(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtClassDef) {
        let qualname = format!("{}.{}", self.owners.last().unwrap().2, item.name);
        let mut declared = node(Language::Python, NodeKind::Class, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.source.line_of(statement.range().start()));
        declared.visibility = python_visibility(item.name.as_str());
        declared.decorators = item
            .decorator_list
            .iter()
            .map(|decorator| qualified_name(&decorator.expression))
            .collect();
        declared.is_abstract = is_contract(item);
        let id = declared.id.clone();
        self.define(&id, statement);
        self.nodes.push(declared);
        for base in item
            .arguments
            .iter()
            .flat_map(|arguments| arguments.args.iter())
        {
            self.reference(
                &id,
                &qualified_name(base),
                EdgeKind::Inherit,
                base.range().start(),
            );
        }
        self.owners.push((id.clone(), NodeKind::Class, qualname));
        self.classes.push(id);
        self.body(&item.body);
        self.classes.pop();
        self.owners.pop();
    }

    /// Record that one declaration names a type, which is a dependency with no other trace.
    ///
    /// An annotation is not called, constructed, or inherited, so without this edge a type used
    /// only in signatures looks unreached by everything. Every typed language has the same shape:
    /// a parameter, a field, or a return states a name it depends on.
    fn annotation(&mut self, source: &str, annotation: &Expr) {
        for name in annotation_names(annotation) {
            self.reference(source, &name, EdgeKind::Typed, annotation.range().start());
        }
    }

    fn callable(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtFunctionDef) {
        let owner = self.owners.last().unwrap().clone();
        let qualname = format!("{}.{}", owner.2, item.name);
        let decorators: Vec<String> = item
            .decorator_list
            .iter()
            .map(|decorator| qualified_name(&decorator.expression))
            .collect();
        let kind = match owner.1 {
            NodeKind::Class
                if decorators
                    .iter()
                    .any(|name| matches!(tail(name), "property" | "cached_property")) =>
            {
                NodeKind::Property
            }
            NodeKind::Class => NodeKind::Method,
            _ => NodeKind::Function,
        };
        let mut declared = node(Language::Python, kind, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.source.line_of(statement.range().start()));
        declared.visibility = python_visibility(item.name.as_str());
        declared.decorators = decorators;
        declared.asynchronous = item.is_async;
        declared.return_annotation = item
            .returns
            .as_ref()
            .map(|returns| annotation_name(returns));
        let id = declared.id.clone();
        self.define(&id, statement);
        self.nodes.push(declared);
        if let Some(returns) = &item.returns {
            self.annotation(&id, returns);
        }
        self.parameters(&id, &qualname, &item.parameters, statement);
        self.owners.push((id, kind, qualname));
        self.types.push(BTreeMap::new());
        self.body(&item.body);
        self.types.pop();
        self.owners.pop();
    }

    fn parameters(
        &mut self,
        function: &str,
        qualname: &str,
        parameters: &Parameters,
        statement: &Stmt,
    ) {
        for (ordinal, (stated, kind)) in python_parameters(parameters).into_iter().enumerate() {
            let name = format!("{qualname}.{}", stated.name());
            let mut declared = parameter(
                Language::Python,
                &name,
                ordinal,
                kind,
                stated.default().is_some(),
            );
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(self.source.line_of(statement.range().start()));
            declared.annotation = stated.annotation().map(annotation_name);
            let annotation = declared.annotation.clone();
            self.declare(stated.name().as_ref(), annotation);
            let id = declared.id.clone();
            self.nodes.push(declared);
            if let Some(declared_type) = stated.annotation() {
                self.annotation(function, declared_type);
            }
            relate(
                &mut self.edges,
                function,
                &id,
                EdgeKind::Define,
                &self.source.relative,
                self.source.line_of(statement.range().start()),
            );
        }
    }

    fn assignment(&mut self, statement: &Stmt, target: &Expr, annotation: Option<String>) {
        let owner = self.owners.last().unwrap().clone();
        let (kind, holder, name) = match target {
            Expr::Name(item) if owner.1 == NodeKind::Module => {
                (NodeKind::Variable, owner.2.clone(), item.id.to_string())
            }
            Expr::Name(item) if owner.1 == NodeKind::Class => {
                (NodeKind::Attribute, owner.2.clone(), item.id.to_string())
            }
            Expr::Attribute(item)
                if matches!(item.value.as_ref(), Expr::Name(receiver)
                    if matches!(receiver.id.as_str(), "self" | "cls"))
                    && !self.classes.is_empty() =>
            {
                let class = self.classes.last().unwrap().clone();
                let qualname = class.rsplit(':').next().unwrap_or_default().to_string();
                (NodeKind::Attribute, qualname, item.attr.to_string())
            }
            _ => return,
        };
        let qualname = format!("{holder}.{name}");
        let mut declared = node(Language::Python, kind, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.source.line_of(statement.range().start()));
        declared.visibility = python_visibility(&name);
        declared.annotation = annotation;
        let id = declared.id.clone();
        let holder_id = identity(
            Language::Python,
            if kind == NodeKind::Variable {
                NodeKind::Module
            } else {
                NodeKind::Class
            },
            &holder,
        );
        if self.nodes.iter().any(|existing| existing.id == id) {
            return;
        }
        self.nodes.push(declared);
        relate(
            &mut self.edges,
            &holder_id,
            &id,
            EdgeKind::Define,
            &self.source.relative,
            self.source.line_of(statement.range().start()),
        );
    }

    fn expression(&mut self, expression: &Expr) {
        if let Expr::Attribute(item) = expression
            && let Expr::Name(receiver) = item.value.as_ref()
            && !matches!(receiver.id.as_str(), "self" | "cls")
        {
            let owner = self.owners.last().unwrap().0.clone();
            self.reference(
                &owner,
                &format!("{}.{}", receiver.id, item.attr),
                EdgeKind::Access,
                item.range().start(),
            );
        }
        if let Expr::Call(item) = expression {
            let caller = self.owners.last().unwrap().0.clone();
            let named = dotted(&item.func).unwrap_or_else(|| self.rendered(&item.func));
            self.reference(&caller, &named, EdgeKind::Call, item.range().start());
        }
        for child in crate::walk::children(expression) {
            self.expression(child);
        }
    }

    /// Return one expression as the single-line text an unresolved reference is named by.
    fn rendered(&self, expression: &Expr) -> String {
        let text = self.source.slice(expression.range());
        let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
        normalize_quotes(&collapsed)
    }

    /// Return the type the receiver of one expression was declared with, if the scope said.
    fn declared_type(&self, expression: &str) -> Option<String> {
        let receiver = expression.split('.').next()?;
        self.types
            .iter()
            .rev()
            .find_map(|scope| scope.get(receiver))
            .cloned()
    }

    /// Remember that one name in the current scope holds a value of one declared type.
    fn declare(&mut self, name: &str, annotation: Option<String>) {
        if let Some(kind) = annotation.filter(|kind| !kind.is_empty())
            && let Some(scope) = self.types.last_mut()
        {
            scope.insert(name.to_string(), kind);
        }
    }

    fn define(&mut self, target: &str, statement: &Stmt) {
        let owner = self.owners.last().unwrap().0.clone();
        relate(
            &mut self.edges,
            &owner,
            target,
            EdgeKind::Define,
            &self.source.relative,
            self.source.line_of(statement.range().start()),
        );
    }

    fn reference(
        &mut self,
        source: &str,
        expression: &str,
        kind: EdgeKind,
        offset: ruff_text_size::TextSize,
    ) {
        if expression.is_empty() {
            return;
        }
        self.references.push(Reference {
            language: Language::Python,
            source: source.to_string(),
            expression: expression.to_string(),
            module: self.module.clone(),
            owner: self
                .classes
                .last()
                .map(|class| class.rsplit(':').next().unwrap_or_default().to_string()),
            receiver_type: self.declared_type(expression),
            kind,
            path: self.source.relative.clone(),
            line: self.source.line_of(offset),
        });
    }
}

/// Return one rendered expression with plain double-quoted strings restated in single quotes.
///
/// The oracle prints through the Python unparser, which always chooses a single quote. Matching
/// that keeps two producers naming the same unresolved expression identically.
fn normalize_quotes(text: &str) -> String {
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
fn python_parameters(stated: &Parameters) -> Vec<(AnyParameterRef<'_>, ParameterKind)> {
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
fn dotted(expression: &Expr) -> Option<String> {
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
fn annotation_names(annotation: &Expr) -> Vec<String> {
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

fn tail(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}

fn is_type_checking(test: &Expr) -> bool {
    match test {
        Expr::Name(name) => name.id.as_str() == "TYPE_CHECKING",
        Expr::Attribute(item) => item.attr.as_str() == "TYPE_CHECKING",
        _ => false,
    }
}

/// Resolve one reference against the repository, leaving what cannot be proved visible.
fn resolve(
    reference: &Reference,
    symbols: &BTreeSet<String>,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let empty = BTreeMap::new();
    let local = aliases.get(&reference.module).unwrap_or(&empty);
    let expanded = match reference.kind {
        EdgeKind::Import => reference.expression.clone(),
        _ => expand(&reference.expression, local),
    };
    let receiver = reference.expression.split('.').next().unwrap_or_default();
    let members = reference.expression.split_once('.').map(|(_, rest)| rest);
    let typed = match (&reference.receiver_type, members) {
        (Some(kind), Some(rest)) => {
            let resolved = expand(kind, local);
            Some(vec![
                format!("{resolved}.{rest}"),
                format!("{}.{resolved}.{rest}", reference.module),
            ])
        }
        _ => None,
    };
    let owned = match (&reference.owner, receiver) {
        (Some(owner), "self" | "cls") => members.map(|rest| format!("{owner}.{rest}")),
        _ => None,
    };
    let mut candidates = Vec::new();
    if reference.kind == EdgeKind::Import {
        candidates.extend(through_reexport(&expanded, aliases, symbols));
        let parts: Vec<&str> = expanded.split('.').collect();
        candidates.extend((1..=parts.len()).rev().map(|size| parts[..size].join(".")));
    } else {
        candidates.extend(typed.into_iter().flatten());
        candidates.extend([
            owned.unwrap_or_default(),
            format!("{}.{expanded}", reference.module),
            expanded.clone(),
            reference.expression.clone(),
        ]);
    }
    if attach(reference, &candidates, symbols, nodes, edges) {
        return;
    }
    let roots: BTreeSet<&str> = local
        .values()
        .map(|target| target.split('.').next().unwrap_or(target))
        .collect();
    let head = expanded.split('.').next().unwrap_or(&expanded);
    let (kind, qualname) = match reference.kind {
        EdgeKind::Import => (
            NodeKind::ExternalModule,
            expanded.split('.').next().unwrap_or(&expanded).to_string(),
        ),
        _ if !reference.expression.contains('.') && is_builtin(&reference.expression) => (
            NodeKind::ExternalSymbol,
            format!("builtins.{}", reference.expression),
        ),
        _ if roots.contains(head) && is_dotted_path(&expanded) => {
            (NodeKind::ExternalSymbol, expanded)
        }
        _ => (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", reference.module, reference.expression),
        ),
    };
    stray(reference, kind, &qualname, nodes, edges);
}

/// Attach one reference to the first candidate name the repository actually declares.
///
/// Every language proposes its own candidates, since only it knows how a name is spelled and what
/// an alias or a receiver turns it into. What happens once a candidate lands is the same
/// everywhere, including the one relation that changes meaning on arrival: calling a class
/// constructs it.
pub fn attach(
    reference: &Reference,
    candidates: &[String],
    symbols: &BTreeSet<String>,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) -> bool {
    let Some(qualname) = candidates
        .iter()
        .find(|candidate| !candidate.is_empty() && symbols.contains(*candidate))
    else {
        return false;
    };
    let kind = target_kind(reference.language, qualname, nodes);
    let relation = match (reference.kind, kind) {
        (EdgeKind::Call, NodeKind::Class) => EdgeKind::Instantiate,
        (kind, _) => kind,
    };
    edges.push(Edge {
        source: reference.source.clone(),
        target: identity(reference.language, kind, qualname),
        kind: relation,
        path: reference.path.clone(),
        line: reference.line,
        resolution: Resolution::Exact,
    });
    true
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
        path: reference.path.clone(),
        line: reference.line,
        resolution: if kind == NodeKind::UnresolvedSymbol {
            Resolution::Unresolved
        } else {
            Resolution::External
        },
    });
}

/// Return the module that actually defines a symbol a package hands on, when one does.
///
/// A package initializer that says `from .decorators import rule` makes `from mypackage import
/// rule` reach `mypackage.decorators`, and a dependency graph that stopped at the package would
/// report an edge to a file holding one line of re-export. Following it is what makes the arrow
/// point at the code that would have to change.
///
/// The walk is bounded because a re-export can chain, and a package that re-exports its own name
/// back would otherwise loop.
fn through_reexport(
    expression: &str,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    modules: &BTreeSet<String>,
) -> Option<String> {
    let mut current = expression.to_string();
    for _ in 0..8 {
        let (holder, symbol) = current.rsplit_once('.')?;
        if !modules.contains(holder) {
            return None;
        }
        let bound = aliases.get(holder)?.get(symbol)?;
        let (defining, _) = bound.rsplit_once('.')?;
        if defining == holder || !modules.contains(defining) {
            return None;
        }
        if !aliases
            .get(defining)
            .is_some_and(|held| held.contains_key(symbol))
        {
            return Some(defining.to_string());
        }
        current = bound.clone();
    }
    None
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
fn is_dotted_path(expression: &str) -> bool {
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
fn is_builtin(name: &str) -> bool {
    const NAMES: &[&str] = &[
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
    NAMES.contains(&name)
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

#[cfg(test)]
mod tests {
    use super::*;

    fn graph_of(source: &str) -> Graph {
        build(
            "repo",
            &[
                Document {
                    relative: "pkg/__init__.py".to_string(),
                    source: String::new(),
                },
                Document {
                    relative: "pkg/example.py".to_string(),
                    source: source.to_string(),
                },
            ],
        )
    }

    fn count(graph: &Graph, kind: NodeKind) -> usize {
        graph.nodes.iter().filter(|node| node.kind == kind).count()
    }

    fn relations(graph: &Graph, kind: EdgeKind) -> usize {
        graph.edges.iter().filter(|edge| edge.kind == kind).count()
    }

    #[test]
    fn the_workspace_holds_the_repository_its_directories_and_its_files() {
        let graph = graph_of("value = 1\n");

        assert_eq!(count(&graph, NodeKind::Repository), 1);
        assert_eq!(count(&graph, NodeKind::Directory), 1);
        assert_eq!(count(&graph, NodeKind::File), 2);
        assert_eq!(count(&graph, NodeKind::Module), 2);
        assert_eq!(count(&graph, NodeKind::Variable), 1);
    }

    #[test]
    fn a_class_carries_its_members_its_bases_and_its_parameters() {
        let graph = graph_of(
            "class Base:\n    pass\n\n\nclass Engine(Base):\n    limit: int = 3\n\n    def run(self, count):\n        self.total = count\n\n    @property\n    def size(self):\n        return 1\n",
        );

        assert_eq!(count(&graph, NodeKind::Class), 2);
        assert_eq!(count(&graph, NodeKind::Method), 1);
        assert_eq!(count(&graph, NodeKind::Property), 1);
        assert_eq!(count(&graph, NodeKind::Attribute), 2);
        assert_eq!(count(&graph, NodeKind::Parameter), 3);
        assert_eq!(relations(&graph, EdgeKind::Inherit), 1);
        assert!(
            graph
                .nodes
                .iter()
                .any(|node| node.id == "python:method:pkg.example.Engine.run")
        );
    }

    #[test]
    fn a_call_resolves_to_a_definition_and_a_constructor_becomes_an_instantiation() {
        let graph = graph_of(
            "class Engine:\n    pass\n\n\ndef build():\n    return Engine()\n\n\ndef start():\n    return build()\n",
        );

        assert_eq!(relations(&graph, EdgeKind::Instantiate), 1);
        assert_eq!(relations(&graph, EdgeKind::Call), 1);
    }

    #[test]
    fn an_unresolved_call_stays_visible_rather_than_being_dropped() {
        let graph = graph_of("def run(handler):\n    return handler()\n");

        assert_eq!(count(&graph, NodeKind::UnresolvedSymbol), 1);
        assert!(
            graph
                .nodes
                .iter()
                .any(|node| node.qualname == "pkg.example::handler")
        );
        assert!(
            graph
                .edges
                .iter()
                .any(|edge| edge.resolution == Resolution::Unresolved)
        );
    }

    #[test]
    fn a_type_checking_branch_contributes_no_runtime_structure() {
        let graph = graph_of(
            "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from other import Thing\nelse:\n    Thing = None\n",
        );
        let imports: Vec<&Edge> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import)
            .collect();

        assert_eq!(imports.len(), 1);
        assert!(imports[0].target.contains("typing"));
    }

    #[test]
    fn an_import_of_a_reexported_symbol_reaches_what_defines_it() {
        let graph = build(
            "repo",
            &[
                Document {
                    relative: "pkg/__init__.py".to_string(),
                    source: "from .decorators import rule\n".to_string(),
                },
                Document {
                    relative: "pkg/decorators.py".to_string(),
                    source: "def rule():\n    pass\n".to_string(),
                },
                Document {
                    relative: "pkg/api.py".to_string(),
                    source: "from pkg import rule\n".to_string(),
                },
            ],
        );
        let reached: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import && edge.path == "pkg/api.py")
            .map(|edge| edge.target.as_str())
            .collect();

        assert_eq!(reached, vec!["python:module:pkg.decorators"]);
    }

    #[test]
    fn a_relative_import_resolves_against_its_own_package() {
        let graph = build(
            "repo",
            &[
                Document {
                    relative: "pkg/__init__.py".to_string(),
                    source: String::new(),
                },
                Document {
                    relative: "pkg/api.py".to_string(),
                    source: "from .models import User\n".to_string(),
                },
                Document {
                    relative: "pkg/models.py".to_string(),
                    source: "class User:\n    pass\n".to_string(),
                },
            ],
        );

        assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Import
            && edge.source == "python:module:pkg.api"
            && edge.target == "python:module:pkg.models"));
    }
}

/// Where the declarations of one module are used across the whole repository.
///
/// A declaration that nothing reaches, one that only its own file reaches, and one that a dozen
/// packages reach are three different things, and only the whole graph can tell them apart. The
/// summary carries the spread as counts so a rule decides what each spread means.
#[derive(Debug, Serialize)]
pub struct Reach {
    pub module: String,
    pub path: String,
    pub language: Language,
    pub is_test_module: bool,
    pub declarations: Vec<Declaration>,
}

#[derive(Debug, Serialize)]
pub struct Declaration {
    pub qualname: String,
    pub kind: String,
    pub is_module_scope: bool,
    pub is_decorated: bool,
    pub visibility: Visibility,
    pub own_file_references: usize,
    pub other_file_references: usize,
    pub referencing_files: usize,
    pub referencing_directories: usize,
    pub referencing_packages: usize,
    pub call_count: usize,
    pub instantiate_count: usize,
    pub inherit_count: usize,
    pub import_count: usize,
}

/// Summarize, for every declaration, how far the references that reach it spread.
pub fn reach(graph: &Graph) -> Vec<Reach> {
    let modules: BTreeMap<&str, &str> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Module)
        .filter_map(|node| Some((node.path.as_deref()?, node.qualname.as_str())))
        .collect();
    let packages: BTreeMap<&str, &str> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Module)
        .filter_map(|node| {
            let separator = node.language?.separator();
            let root = node.qualname.split(separator).next()?;
            Some((node.path.as_deref()?, root))
        })
        .collect();
    let owners: BTreeMap<&str, &str> = graph
        .nodes
        .iter()
        .filter_map(|node| {
            let (owner, _) = node.qualname.rsplit_once(node.language?.separator())?;
            Some((node.id.as_str(), owner))
        })
        .collect();
    let by_qualname: BTreeMap<&str, &str> = graph
        .nodes
        .iter()
        .map(|node| (node.qualname.as_str(), node.id.as_str()))
        .collect();
    let mut arrivals: BTreeMap<&str, Vec<&Edge>> = BTreeMap::new();
    for edge in &graph.edges {
        if matches!(edge.kind, EdgeKind::Contain | EdgeKind::Define) {
            continue;
        }
        arrivals.entry(edge.target.as_str()).or_default().push(edge);
        // Reaching a member reaches what declares it. An enum read by one of its names, and a
        // class reached through one method, are both uses of the declaration that holds them.
        if let Some(owner) = owners.get(edge.target.as_str())
            && let Some(holder) = by_qualname.get(owner)
        {
            arrivals.entry(holder).or_default().push(edge);
        }
    }
    let mut grouped: BTreeMap<String, Reach> = BTreeMap::new();
    for node in &graph.nodes {
        let kind = match node.kind {
            NodeKind::Class => "class",
            NodeKind::Function => "function",
            NodeKind::Method => "method",
            NodeKind::Property => "property",
            NodeKind::Variable => "variable",
            NodeKind::Attribute => "attribute",
            _ => continue,
        };
        let (Some(path), Some(language)) = (node.path.as_deref(), node.language) else {
            continue;
        };
        let reaching = arrivals
            .get(node.id.as_str())
            .map(Vec::as_slice)
            .unwrap_or_default();
        let entry = grouped.entry(path.to_string()).or_insert_with(|| Reach {
            module: path.to_string(),
            path: path.to_string(),
            language,
            is_test_module: is_test_path(language, path),
            declarations: Vec::new(),
        });
        entry.declarations.push(declaration(
            node,
            kind,
            path,
            reaching,
            &packages,
            modules.get(path).copied().unwrap_or_default(),
        ));
    }
    grouped.into_values().collect()
}

fn declaration(
    node: &Node,
    kind: &str,
    path: &str,
    reaching: &[&Edge],
    packages: &BTreeMap<&str, &str>,
    module: &str,
) -> Declaration {
    let own = reaching.iter().filter(|edge| edge.path == path).count();
    let files: BTreeSet<&str> = reaching.iter().map(|edge| edge.path.as_str()).collect();
    let directories: BTreeSet<&str> = files.iter().map(|file| directory_of(file)).collect();
    let reached_from: BTreeSet<&str> = files
        .iter()
        .map(|file| packages.get(file).copied().unwrap_or(*file))
        .collect();
    let separator = node.language.map_or(".", Language::separator);
    Declaration {
        qualname: node.qualname.clone(),
        kind: kind.to_string(),
        is_module_scope: node
            .qualname
            .rsplit_once(separator)
            .is_some_and(|(owner, _)| owner == module),
        is_decorated: !node.decorators.is_empty(),
        visibility: node.visibility,
        own_file_references: own,
        other_file_references: reaching.len() - own,
        referencing_files: files.len(),
        referencing_directories: directories.len(),
        referencing_packages: reached_from.len(),
        call_count: reaching
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Call)
            .count(),
        instantiate_count: reaching
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Instantiate)
            .count(),
        inherit_count: reaching
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Inherit)
            .count(),
        import_count: reaching
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import)
            .count(),
    }
}

fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

/// Whether a test runner collects one file rather than other code calling into it.
///
/// Each language marks this somewhere a path can see. Python names the file, Rust puts an
/// integration test under `tests/`, and a TypeScript runner looks for the suffix in the name. A
/// Rust unit test is not here at all, because it lives in a nested module inside the file it
/// exercises, and being nested is already enough to keep it out of what this rule judges.
fn is_test_path(language: Language, relative: &str) -> bool {
    let name = relative.rsplit('/').next().unwrap_or(relative);
    match language {
        Language::Python => crate::python::is_test_path(relative),
        Language::Rust => relative.starts_with("tests/") || relative.contains("/tests/"),
        Language::TypeScript => name.contains(".test.") || name.contains(".spec."),
        Language::C | Language::Cpp | Language::Cuda => {
            name.starts_with("test_") || name.contains("_test.")
        }
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
fn is_contract(item: &ruff_python_ast::StmtClassDef) -> bool {
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
fn python_visibility(name: &str) -> Visibility {
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
