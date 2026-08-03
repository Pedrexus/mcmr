use super::record::Coupling;
use crate::graph::{Graph, Node, NodeKind};
use crate::modules::ModuleImports;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// The import arrows of the repository beside the types each module declares.
pub(super) struct Modules<'repository> {
    imports: ModuleImports<'repository>,
    types: BTreeMap<&'repository str, Vec<&'repository Node>>,
}

impl<'repository> Modules<'repository> {
    pub(super) fn of(graph: &'repository Graph) -> Self {
        let mut types: BTreeMap<&str, Vec<&Node>> = BTreeMap::new();
        for node in &graph.nodes {
            if node.kind == NodeKind::Class
                && let Some(path) = node.path.as_deref()
            {
                types.entry(path).or_default().push(node);
            }
        }
        Self {
            imports: ModuleImports::of(graph),
            types,
        }
    }

    pub(super) fn facts(&self) -> Vec<Value> {
        self.imports
            .declared()
            .iter()
            .map(|(path, node)| self.fact(path, node))
            .collect()
    }

    fn dependencies(&self, path: &str) -> Vec<Coupling> {
        self.imports
            .imports(path)
            .into_iter()
            .map(|target| Coupling {
                module: self.imports.name(target).to_string(),
                afferent_count: self.imports.importers(target).len(),
                efferent_count: self.imports.imports(target).len(),
            })
            .collect()
    }

    fn fact(&self, path: &str, module: &Node) -> Value {
        let held = self.types.get(path).map(Vec::as_slice).unwrap_or_default();
        json!({
            "key": format!("coupling:{}", module.qualname),
            "span": {"path": path},
            "language": module
                .language
                .expect("a declared module must state its language"),
            "module": module.qualname,
            "afferent_count": self.imports.importers(path).len(),
            "efferent_count": self.imports.imports(path).len(),
            "declaration_count": held.len(),
            "abstract_declaration_count": held.iter().filter(|node| node.is_abstract).count(),
            "dependencies": self.dependencies(path),
        })
    }
}
