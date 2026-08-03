use super::paths::Specifiers;
use super::paths::{Located, names::ImportedName};
use crate::graph::{
    Edge, EdgeKind, Language, Node, NodeKind, Reference, Resolution, Stated, Visibility, expand,
    identity, node,
};
use crate::source::Source;
use crate::typescript::support::range;
use imports::ImportedBinding;
use owner::Owner;
use oxc_ast::ast::{PropertyKey, TSAccessibility};
use oxc_span::Span;
use relations::{ExactEdge, WrittenReference};
use state::CollectorState;
use std::collections::{BTreeMap, BTreeSet};

/// Collect every definition and reference one TypeScript file states.
///
/// The walk is the parser's own visitor with the declaring nodes overridden, so a construct this
/// frontend says nothing about is still descended into and the calls inside it are still recorded.
pub(super) struct Collector<'ts> {
    source: Source,
    module: String,
    specifiers: &'ts Specifiers,
    state: CollectorState,
}

impl<'ts> Collector<'ts> {
    pub(in crate::typescript::graph::collector) fn reached(
        &mut self,
        located: Located,
        bindings: Vec<ImportedBinding>,
        span: Span,
    ) {
        match located {
            Located::Package(package) => self.package_reached(&package, bindings, span),
            Located::Module(target) => {
                self.repository_reached(&target, bindings, Resolution::Exact, span);
            }
            Located::Unsettled(target) => {
                self.repository_reached(&target, bindings, Resolution::Unresolved, span);
            }
        }
    }

    pub(super) fn new(source: Source, module: String, specifiers: &'ts Specifiers) -> Self {
        let owner = Owner {
            id: identity(Language::TypeScript, NodeKind::Module, &module),
            kind: NodeKind::Module,
            qualname: module.clone(),
        };
        Self {
            source,
            module,
            specifiers,
            state: CollectorState::owned_by(owner),
        }
    }

    /// Return everything this file states, with the names a later export statement raised.
    ///
    /// `export { helper }` is written after the declaration it publishes, so what the declaration
    /// reaches is only settled once the whole file has been read.
    pub(super) fn stated(mut self) -> Stated {
        let prefix = format!("{}.", self.module);
        for declared in &mut self.state.graph.nodes {
            if let Some(name) = declared.qualname.strip_prefix(&prefix)
                && !name.contains('.')
                && self.state.names.exported.contains(name)
            {
                declared.visibility = Visibility::Public;
            }
        }
        Stated {
            nodes: self.state.graph.nodes,
            edges: self.state.graph.edges,
            references: self.state.graph.references,
            export_references: Vec::new(),
            aliases: self.state.names.aliases,
            exports: BTreeSet::new(),
            export_nodes: BTreeMap::new(),
        }
    }

    fn attach_external(&mut self, reference: &WrittenReference<'_>) -> bool {
        let head = reference.expression.split('.').next().unwrap_or_default();
        if !self.state.names.externals.contains_key(head) {
            return false;
        }
        let named = expand(reference.expression, &self.state.names.externals);
        self.outside(
            reference.source,
            NodeKind::ExternalSymbol,
            &named,
            reference.kind,
            reference.span,
        );
        true
    }

    fn bind_package(
        &mut self,
        owner: &Owner,
        package: &str,
        binding: ImportedBinding,
        span: Span,
    ) {
        let held = alias_name(ImportedName {
            module: package,
            member: &binding.name,
        });
        if !binding.name.is_empty() {
            self.outside(
                &owner.id,
                NodeKind::ExternalSymbol,
                &held,
                EdgeKind::Access,
                span,
            );
        }
        self.state.names.externals.insert(binding.bound, held);
    }

    fn bind_repository(
        &mut self,
        owner: &Owner,
        target: &str,
        binding: ImportedBinding,
        resolution: Resolution,
        span: Span,
    ) {
        let imported = ImportedName {
            module: target,
            member: &binding.name,
        };
        let held = alias_name(imported);
        self.import(&owner.id, imported, span);
        if resolution == Resolution::Exact && !binding.name.is_empty() {
            self.reference(WrittenReference {
                source: &owner.id,
                expression: &held,
                kind: EdgeKind::Access,
                span,
            });
        }
        self.state.names.aliases.insert(binding.bound, held);
    }

    fn declare(&mut self, declared: Node, span: Span) -> Owner {
        let holder = self.owner();
        self.declare_for(declared, &holder, span)
    }

    fn declare_for(&mut self, declared: Node, holder: &Owner, span: Span) -> Owner {
        let owner = Owner {
            id: declared.id.clone(),
            kind: declared.kind,
            qualname: declared.qualname.clone(),
        };
        if self.state.graph.placed.insert(owner.id.clone()) {
            self.state.graph.nodes.push(declared);
        }
        self.relate(ExactEdge {
            source: &holder.id,
            target: &owner.id,
            kind: EdgeKind::Define,
            span,
        });
        owner
    }

    fn enter(&mut self, owner: Owner) {
        self.state.owners.push(owner);
    }

    fn import(&mut self, source: &str, imported: ImportedName<'_>, span: Span) {
        let expression = imported.render();
        self.store_reference(WrittenReference {
            source,
            expression: &expression,
            kind: EdgeKind::Import,
            span,
        });
    }

    fn leave(&mut self) {
        self.state.owners.pop();
    }

    fn line(&self, span: Span) -> usize {
        self.source.line_of(range(span).start())
    }

    /// Attach one reference to a declaration outside this repository, which needs no resolution.
    fn outside(
        &mut self,
        source: &str,
        kind: NodeKind,
        qualname: &str,
        relation: EdgeKind,
        span: Span,
    ) {
        let declared = node(Language::TypeScript, kind, qualname);
        let target = declared.id.clone();
        if self.state.graph.placed.insert(target.clone()) {
            self.state.graph.nodes.push(declared);
        }
        self.state.graph.edges.push(Edge {
            source: source.to_string(),
            target,
            kind: relation,
            path: self.source.relative.clone(),
            line: self.line(span),
            resolution: Resolution::External,
        });
    }

    fn owner(&self) -> Owner {
        self.state
            .owners
            .last()
            .cloned()
            .expect("the TypeScript collector must retain its module owner")
    }

    fn package_reached(&mut self, package: &str, bindings: Vec<ImportedBinding>, span: Span) {
        let owner = self.owner();
        self.outside(
            &owner.id,
            NodeKind::ExternalModule,
            package,
            EdgeKind::Import,
            span,
        );
        for binding in bindings {
            self.bind_package(&owner, package, binding, span);
        }
    }

    fn place(&self, kind: NodeKind, named: &str, span: Span, reach: Visibility) -> Node {
        let mut declared = node(
            Language::TypeScript,
            kind,
            &format!("{}.{named}", self.owner().qualname),
        );
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(self.line(span));
        declared.source = matches!(
            kind,
            NodeKind::Method | NodeKind::Property | NodeKind::Attribute
        )
        .then(|| self.rendered(span));
        declared.visibility = reach;
        declared
    }

    /// Return how widely a declaration at this point reaches.
    ///
    /// `export` is what public means at module scope, a class member is as reachable as the class
    /// unless it says otherwise, and anything declared inside a callable is reachable from nowhere
    /// else whatever the file exports.
    fn reach(&self) -> Visibility {
        match self.owner().kind {
            NodeKind::Module if self.state.exporting => Visibility::Public,
            NodeKind::Module => Visibility::Internal,
            NodeKind::Class => Visibility::Public,
            _ => Visibility::Internal,
        }
    }

    /// Record one name this file reaches for, which resolution then joins to a declaration.
    ///
    /// A name bound from a package is the exception, because the import already said where it
    /// comes from. Attaching it here keeps a dependency out of the unresolved set, which is where
    /// a gap in this kernel belongs and nothing else does.
    fn reference(&mut self, reference: WrittenReference<'_>) {
        if reference.expression.is_empty() || self.attach_external(&reference) {
            return;
        }
        self.store_reference(reference);
    }

    fn relate(&mut self, relation: ExactEdge<'_>) {
        self.state.graph.edges.push(Edge {
            source: relation.source.to_string(),
            target: relation.target.to_string(),
            kind: relation.kind,
            path: self.source.relative.clone(),
            line: self.line(relation.span),
            resolution: Resolution::Exact,
        });
    }

    /// Return one span as the single-line text an annotation is written down as.
    fn rendered(&self, span: Span) -> String {
        self.source
            .slice(range(span))
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    }

    fn repository_reached(
        &mut self,
        target: &str,
        bindings: Vec<ImportedBinding>,
        resolution: Resolution,
        span: Span,
    ) {
        let owner = self.owner();
        if bindings.is_empty() {
            self.import(
                &owner.id,
                ImportedName {
                    module: target,
                    member: "",
                },
                span,
            );
        }
        for binding in bindings {
            self.bind_repository(&owner, target, binding, resolution, span);
        }
    }

    fn store_reference(&mut self, reference: WrittenReference<'_>) {
        self.state.graph.references.push(Reference {
            language: Language::TypeScript,
            source: reference.source.to_string(),
            expression: reference.expression.to_string(),
            module: self.module.clone(),
            resolution: crate::graph::ReferenceResolution {
                owner: self.state.classes.last().cloned(),
                receiver_type: None,
                binding_count: 0,
            },
            kind: reference.kind,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: self.line(reference.span),
                module_node: None,
            },
        });
    }
}

fn alias_name(imported: ImportedName<'_>) -> String {
    match imported.member.is_empty() {
        true => imported.module.to_owned(),
        false => imported.render(),
    }
}

mod contracts;
mod declarations;
mod imports;
mod owner;
mod relations;
mod state;
mod visitor;

/// Return the name one class or interface member states, including a private hash.
fn key_name(key: &PropertyKey<'_>) -> Option<String> {
    match key {
        PropertyKey::PrivateIdentifier(held) => Some(format!("#{}", held.name)),
        held => held.static_name().map(|name| name.to_string()),
    }
}

/// Return how widely one class member reaches.
fn member_reach(key: &PropertyKey<'_>, accessibility: Option<TSAccessibility>) -> Visibility {
    if matches!(key, PropertyKey::PrivateIdentifier(_)) {
        return Visibility::Private;
    }
    stated_reach(accessibility)
}

/// Return how widely one declaration reaches from its access modifier.
fn stated_reach(accessibility: Option<TSAccessibility>) -> Visibility {
    match accessibility {
        Some(TSAccessibility::Private) => Visibility::Private,
        Some(TSAccessibility::Protected) => Visibility::Protected,
        _ => Visibility::Public,
    }
}
