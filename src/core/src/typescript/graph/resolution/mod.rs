use super::paths::names::ImportedName;
use super::paths::split_import;
use crate::graph::{Attachment, EdgeKind, NodeKind, Reference, attach, expand, stray};
use std::collections::{BTreeMap, BTreeSet};

pub use context::ResolutionContext;

mod context;
mod provided;

pub fn resolve(reference: &Reference, context: ResolutionContext<'_>) {
    Resolver { reference, context }.resolve();
}

struct Resolver<'reference, 'graph> {
    reference: &'reference Reference,
    context: ResolutionContext<'graph>,
}

impl Resolver<'_, '_> {
    fn attach_modules(&mut self, candidates: &[String]) -> bool {
        attach(
            Attachment {
                reference: self.reference,
                candidates,
                symbols: self.context.modules,
                relation_kind: self.reference.kind,
            },
            self.context.nodes,
            self.context.edges,
        )
    }

    fn attach_symbols(&mut self, candidates: &[String]) -> bool {
        attach(
            Attachment {
                reference: self.reference,
                candidates,
                symbols: self.context.symbols,
                relation_kind: self.reference.kind,
            },
            self.context.nodes,
            self.context.edges,
        )
    }

    fn declaration(&self, imported: ImportedName<'_>) -> Option<String> {
        let mut current = imported.render();
        let mut visited = BTreeSet::new();
        while visited.insert(current.clone()) {
            if self.context.symbols.contains(&current) {
                return Some(current);
            }
            let bound = self.next_alias(&current)?;
            if bound == current {
                return None;
            }
            current = bound;
        }
        None
    }

    fn declared_candidate(&self, expanded: &str) -> Option<String> {
        let (holder, name) = expanded.rsplit_once('.')?;
        self.declaration(ImportedName {
            module: holder,
            member: name,
        })
    }

    fn expanded(&self) -> String {
        self.context
            .aliases
            .get(&self.reference.module)
            .map_or_else(
                || self.reference.expression.clone(),
                |local| expand(&self.reference.expression, local),
            )
    }

    fn import_candidates(&self) -> Vec<String> {
        let (module, symbol) = split_import(&self.reference.expression);
        let mut candidates = Vec::new();
        if !symbol.is_empty()
            && let Some(found) = self.declaration(ImportedName {
                module,
                member: symbol,
            })
            && let Some((holder, _)) = found.rsplit_once('.')
            && self.context.modules.contains(holder)
        {
            candidates.push(holder.to_string());
        }
        candidates.push(module.to_string());
        candidates
    }

    fn known(&self, candidate: &str) -> bool {
        self.context.symbols.contains(candidate)
            || candidate
                .rsplit_once('.')
                .and_then(|(owner, name)| {
                    Some(self.context.aliases.get(owner)?.contains_key(name))
                })
                .unwrap_or(false)
    }

    fn next_alias(&self, current: &str) -> Option<String> {
        let (owner, symbol) = current.rsplit_once('.')?;
        let held = self.context.aliases.get(owner)?;
        held.get(symbol)
            .cloned()
            .or_else(|| self.starred(held, symbol))
    }

    fn receiver_candidate(&self) -> Option<String> {
        let holder = self.reference.resolution.owner.as_ref()?;
        let member = self.reference.expression.strip_prefix("this.")?;
        Some(format!("{holder}.{member}"))
    }

    fn record_stray(&mut self, kind: NodeKind, qualname: String) {
        stray(
            self.reference,
            kind,
            &qualname,
            self.context.nodes,
            self.context.edges,
        );
    }

    fn resolve(mut self) {
        match self.reference.kind == EdgeKind::Import {
            true => self.resolve_import(),
            false => self.resolve_symbol(),
        }
    }

    fn resolve_import(&mut self) {
        let candidates = self.import_candidates();
        if self.attach_modules(&candidates) {
            return;
        }
        let (module, _) = split_import(&self.reference.expression);
        self.record_stray(
            NodeKind::UnresolvedSymbol,
            format!("{}::{module}", self.reference.module),
        );
    }

    fn resolve_symbol(&mut self) {
        let candidates = self.symbol_candidates();
        if self.attach_symbols(&candidates) {
            return;
        }
        let (kind, qualname) = self.unresolved();
        self.record_stray(kind, qualname);
    }

    fn starred(&self, held: &BTreeMap<String, String>, symbol: &str) -> Option<String> {
        held.iter()
            .filter(|(key, _)| key.starts_with("* "))
            .map(|(_, target)| {
                ImportedName {
                    module: target,
                    member: symbol,
                }
                .render()
            })
            .find(|candidate| self.known(candidate))
    }

    fn symbol_candidates(&self) -> Vec<String> {
        let expanded = self.expanded();
        let mut candidates = Vec::new();
        candidates.extend(self.receiver_candidate());
        candidates.push(expanded.clone());
        candidates.extend(self.declared_candidate(&expanded));
        candidates.extend(self.written_candidates(&expanded));
        candidates
    }

    fn unresolved(&self) -> (NodeKind, String) {
        let head = self
            .reference
            .expression
            .split('.')
            .next()
            .unwrap_or_default();
        match provided::contains(head) {
            true => (
                NodeKind::ExternalSymbol,
                format!("globalThis.{}", self.reference.expression),
            ),
            false => (
                NodeKind::UnresolvedSymbol,
                format!("{}::{}", self.reference.module, self.reference.expression),
            ),
        }
    }

    fn written_candidates(&self, expanded: &str) -> [String; 3] {
        [
            ImportedName {
                module: &self.reference.module,
                member: expanded,
            }
            .render(),
            ImportedName {
                module: &self.reference.module,
                member: &self.reference.expression,
            }
            .render(),
            self.reference.expression.clone(),
        ]
    }
}
