use super::construction::identity;
use super::contracts::{Edge, EdgeKind, Graph, Language, Node, NodeKind, Visibility};
use crate::protocol::Span;
use crate::source::is_test_path;
use std::collections::{BTreeMap, BTreeSet};

mod counts;
mod declaration;
mod indexes;
mod kind;
mod links;
mod reachable;
mod spread;
mod summary;

pub use counts::DeclarationCounts;
use counts::ReferenceOwnership;
pub use declaration::Declaration;
use declaration::{DeclarationContext, OwnerContract};
use indexes::ReachIndexes;
use kind::DeclarationKind;
use links::ReachLinks;
use reachable::Reachable;
use spread::ReferenceSpread;
pub use summary::Reach;

/// Summarize how far every declaration reaches across the repository.
pub fn reach(graph: &Graph) -> Vec<Reach> {
    ReachIndex::summarize(graph)
}

struct ReachIndex<'a> {
    indexes: ReachIndexes<'a>,
    registered: BTreeSet<String>,
    enum_classes: BTreeSet<&'a str>,
    arrivals: BTreeMap<&'a str, Vec<&'a Edge>>,
    grouped: BTreeMap<String, Reach>,
}

impl<'a> ReachIndex<'a> {
    pub(super) fn summarize(graph: &'a Graph) -> Vec<Reach> {
        let mut index = Self::new(graph);
        for node in &graph.nodes {
            index.record(node);
        }
        index.grouped.into_values().collect()
    }

    fn arrivals(graph: &'a Graph, links: &ReachLinks<'a>) -> BTreeMap<&'a str, Vec<&'a Edge>> {
        let mut arrivals = BTreeMap::new();
        for edge in &graph.edges {
            Self::record_arrival(&mut arrivals, edge, links);
        }
        arrivals
    }

    fn by_qualname(graph: &'a Graph) -> BTreeMap<&'a str, &'a str> {
        graph
            .nodes
            .iter()
            .map(|node| (node.qualname.as_str(), node.id.as_str()))
            .collect()
    }

    fn enum_classes(graph: &'a Graph) -> BTreeSet<&'a str> {
        let mut enums = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Inherit && Self::is_enum_base(&edge.target))
            .map(|edge| edge.source.clone())
            .collect::<BTreeSet<_>>();
        enums.extend(
            graph
                .nodes
                .iter()
                .filter(|node| node.is_enum)
                .map(|node| node.id.clone()),
        );
        while Self::extend_registered(graph, &mut enums) {}
        graph
            .nodes
            .iter()
            .filter(|node| enums.contains(&node.id))
            .map(|node| node.qualname.as_str())
            .collect()
    }

    fn extend_registered(graph: &Graph, registered: &mut BTreeSet<String>) -> bool {
        let inherited = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Inherit && registered.contains(&edge.target))
            .map(|edge| edge.source.clone())
            .collect::<Vec<_>>();
        let before = registered.len();
        registered.extend(inherited);
        registered.len() > before
    }

    fn is_enum_base(target: &str) -> bool {
        matches!(
            target.rsplit('.').next().unwrap_or(target),
            "Enum" | "Flag" | "IntEnum" | "IntFlag" | "ReprEnum" | "StrEnum"
        )
    }

    fn modules(graph: &'a Graph) -> BTreeMap<&'a str, &'a str> {
        graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Module)
            .filter_map(|node| Some((node.path.as_deref()?, node.qualname.as_str())))
            .collect()
    }

    fn new(graph: &'a Graph) -> Self {
        let owners = Self::owners(graph);
        let by_qualname = Self::by_qualname(graph);
        let links = ReachLinks {
            owners,
            by_qualname,
        };
        Self {
            indexes: ReachIndexes {
                modules: Self::modules(graph),
                packages: Self::packages(graph),
                visibility: Self::visibility(graph),
                qualnames: graph
                    .nodes
                    .iter()
                    .map(|node| (node.id.as_str(), node.qualname.as_str()))
                    .collect(),
                identities: Self::by_qualname(graph),
                unresolved_names: Self::unresolved_names(graph),
                inheritance_owners: graph
                    .edges
                    .iter()
                    .filter(|edge| edge.kind == EdgeKind::Inherit)
                    .flat_map(|edge| [edge.source.as_str(), edge.target.as_str()])
                    .collect(),
            },
            registered: Self::registered_declarations(graph),
            enum_classes: Self::enum_classes(graph),
            arrivals: Self::arrivals(graph, &links),
            grouped: BTreeMap::new(),
        }
    }

    fn owner(reachable: Reachable<'_>) -> Option<&str> {
        reachable
            .node
            .qualname
            .rsplit_once(reachable.language.separator())
            .map(|(owner, _)| owner)
    }

    fn owners(graph: &'a Graph) -> BTreeMap<&'a str, &'a str> {
        graph
            .nodes
            .iter()
            .filter_map(|node| {
                let (owner, _) = node.qualname.rsplit_once(node.language?.separator())?;
                Some((node.id.as_str(), owner))
            })
            .collect()
    }

    fn packages(graph: &'a Graph) -> BTreeMap<&'a str, &'a str> {
        graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Module)
            .filter_map(|node| {
                let root = node.qualname.split(node.language?.separator()).next()?;
                Some((node.path.as_deref()?, root))
            })
            .collect()
    }

    fn record_arrival(
        arrivals: &mut BTreeMap<&'a str, Vec<&'a Edge>>,
        edge: &'a Edge,
        links: &ReachLinks<'a>,
    ) {
        if matches!(edge.kind, EdgeKind::Contain | EdgeKind::Define) {
            return;
        }
        arrivals.entry(edge.target.as_str()).or_default().push(edge);
        if let Some(owner) = links.owners.get(edge.target.as_str())
            && let Some(holder) = links.by_qualname.get(owner)
        {
            arrivals.entry(holder).or_default().push(edge);
        }
    }

    fn registered_declarations(graph: &Graph) -> BTreeSet<String> {
        let mut registered = graph
            .nodes
            .iter()
            .filter(|node| {
                node.decorators
                    .iter()
                    .any(|decorator| decorator == "registered-component")
            })
            .map(|node| node.id.clone())
            .collect::<BTreeSet<_>>();
        while Self::extend_registered(graph, &mut registered) {}
        registered
    }

    fn span(node: &Node, path: &str) -> Span {
        let line = node.line.expect("a source declaration has a line");
        Span {
            path: path.to_string(),
            start_line: line,
            start_column: 0,
            end_line: line,
            end_column: 0,
        }
    }

    fn unresolved_names(graph: &Graph) -> BTreeMap<String, usize> {
        let names = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::UnresolvedSymbol)
            .map(|node| {
                (
                    node.id.as_str(),
                    node.qualname
                        .rsplit(['.', ':'])
                        .find(|part| !part.is_empty())
                        .unwrap_or_default()
                        .to_string(),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let mut counts = BTreeMap::new();
        for edge in &graph.edges {
            if let Some(name) = names.get(edge.target.as_str()) {
                *counts.entry(name.clone()).or_default() += 1;
            }
        }
        counts
    }

    fn visibility(graph: &'a Graph) -> BTreeMap<&'a str, Visibility> {
        graph
            .nodes
            .iter()
            .map(|node| (node.id.as_str(), node.visibility))
            .collect()
    }

    fn declaration(&self, reachable: Reachable<'_>, reaching: &[&Edge]) -> Declaration {
        let owner = Self::owner(reachable);
        let (owner_references, non_owner_references) =
            self.owner_reference_counts(reachable, reaching, owner);
        let name = reachable
            .node
            .qualname
            .rsplit(reachable.language.separator())
            .next()
            .unwrap_or_default();
        Declaration {
            qualname: reachable.node.qualname.clone(),
            kind: reachable.kind.as_str().to_string(),
            context: DeclarationContext {
                span: Self::span(reachable.node, reachable.path),
                is_module_scope: self.is_module_scope(reachable),
                is_decorated: !reachable.node.decorators.is_empty()
                    || self.registered.contains(&reachable.node.id),
            },
            visibility: self.effective_visibility(reachable.node),
            owner: OwnerContract {
                visibility: owner
                    .and_then(|qualname| self.identity(qualname))
                    .and_then(|id| self.indexes.visibility.get(id).copied())
                    .unwrap_or(Visibility::Public),
                has_inheritance: owner
                    .and_then(|qualname| self.identity(qualname))
                    .is_some_and(|id| self.indexes.inheritance_owners.contains(id)),
            },
            counts: declaration_counts(
                reaching,
                reachable.path,
                &self.indexes.packages,
                ReferenceOwnership {
                    owner_references,
                    non_owner_references,
                    unresolved_name_references: self
                        .indexes
                        .unresolved_names
                        .get(name)
                        .copied()
                        .unwrap_or_default(),
                },
            ),
        }
    }

    fn effective_visibility(&self, node: &Node) -> Visibility {
        if node.visibility != Visibility::Public || node.language != Some(Language::Rust) {
            return node.visibility;
        }
        let mut owner = node.qualname.rsplit_once("::").map(|(owner, _)| owner);
        while let Some(qualname) = owner {
            let module = identity(Language::Rust, NodeKind::Module, qualname);
            if self
                .indexes
                .visibility
                .get(module.as_str())
                .is_some_and(|reach| *reach != Visibility::Public)
            {
                return Visibility::Internal;
            }
            owner = qualname.rsplit_once("::").map(|(parent, _)| parent);
        }
        Visibility::Public
    }

    fn identity(&self, qualname: &str) -> Option<&str> {
        self.indexes.identities.get(qualname).copied()
    }

    fn is_enum_member(&self, node: &Node) -> bool {
        node.kind == NodeKind::Attribute
            && node
                .language
                .and_then(|language| node.qualname.rsplit_once(language.separator()))
                .is_some_and(|(owner, _)| self.enum_classes.contains(owner))
    }

    fn is_module_scope(&self, reachable: Reachable<'_>) -> bool {
        let module = self
            .indexes
            .modules
            .get(reachable.path)
            .copied()
            .unwrap_or_default();
        let separator = reachable.node.language.map_or(".", Language::separator);
        reachable
            .node
            .qualname
            .rsplit_once(separator)
            .is_some_and(|(owner, _)| owner == module)
    }

    fn owner_reference_counts(
        &self,
        reachable: Reachable<'_>,
        reaching: &[&Edge],
        owner: Option<&str>,
    ) -> (usize, usize) {
        let Some(owner) = owner else {
            return (0, reaching.len());
        };
        let prefix = format!("{owner}{}", reachable.language.separator());
        let owned = reaching
            .iter()
            .filter(|edge| {
                self.indexes
                    .qualnames
                    .get(edge.source.as_str())
                    .is_some_and(|source| *source == owner || source.starts_with(&prefix))
            })
            .count();
        (owned, reaching.len() - owned)
    }

    fn reachable(&self, node: &'a Node) -> Option<Reachable<'a>> {
        if self.is_enum_member(node) {
            return None;
        }
        let kind = match node.kind {
            NodeKind::Class => DeclarationKind::Class,
            NodeKind::Function => DeclarationKind::Function,
            NodeKind::Method => DeclarationKind::Method,
            NodeKind::Property => DeclarationKind::Property,
            NodeKind::Variable => DeclarationKind::Variable,
            NodeKind::Attribute => DeclarationKind::Attribute,
            _ => return None,
        };
        Some(Reachable {
            node,
            path: node.path.as_deref()?,
            language: node.language?,
            kind,
        })
    }

    fn record(&mut self, node: &'a Node) {
        let Some(reachable) = self.reachable(node) else {
            return;
        };
        let reaching = self
            .arrivals
            .get(node.id.as_str())
            .map(Vec::as_slice)
            .unwrap_or_default();
        let declaration = self.declaration(reachable, reaching);
        self.summary(reachable).declarations.push(declaration);
    }

    fn summary(&mut self, reachable: Reachable<'_>) -> &mut Reach {
        self.grouped
            .entry(reachable.path.to_string())
            .or_insert_with(|| Reach {
                module: reachable.path.to_string(),
                path: reachable.path.to_string(),
                language: reachable.language,
                is_test_module: is_test_path(reachable.path),
                declarations: Vec::new(),
            })
    }
}

fn declaration_counts(
    reaching: &[&Edge],
    path: &str,
    packages: &BTreeMap<&str, &str>,
    ownership: ReferenceOwnership,
) -> DeclarationCounts {
    let spread = reference_spread(reaching, path, packages);
    DeclarationCounts {
        references: counts::ReferenceCounts {
            own_file_references: spread.own,
            other_file_references: spread.other,
            ownership,
            referencing_files: spread.files,
            referencing_directories: spread.directories,
            referencing_packages: spread.packages,
        },
        uses: counts::UseCounts {
            call_count: edge_count(reaching, EdgeKind::Call),
            instantiate_count: edge_count(reaching, EdgeKind::Instantiate),
            inherit_count: edge_count(reaching, EdgeKind::Inherit),
            import_count: edge_count(reaching, EdgeKind::Import),
        },
    }
}

fn reference_spread(
    reaching: &[&Edge],
    path: &str,
    packages: &BTreeMap<&str, &str>,
) -> ReferenceSpread {
    let own = reaching.iter().filter(|edge| edge.path == path).count();
    let files = referencing_files(reaching);
    ReferenceSpread {
        own,
        other: reaching.len() - own,
        files: files.len(),
        directories: referencing_directories(&files),
        packages: referencing_packages(&files, packages),
    }
}

fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

fn edge_count(edges: &[&Edge], kind: EdgeKind) -> usize {
    edges.iter().filter(|edge| edge.kind == kind).count()
}

fn referencing_directories(files: &BTreeSet<&str>) -> usize {
    files
        .iter()
        .map(|file| directory_of(file))
        .collect::<BTreeSet<_>>()
        .len()
}

fn referencing_files<'b>(reaching: &[&'b Edge]) -> BTreeSet<&'b str> {
    reaching.iter().map(|edge| edge.path.as_str()).collect()
}

fn referencing_packages(files: &BTreeSet<&str>, packages: &BTreeMap<&str, &str>) -> usize {
    files
        .iter()
        .map(|file| packages.get(file).copied().unwrap_or(*file))
        .collect::<BTreeSet<_>>()
        .len()
}
