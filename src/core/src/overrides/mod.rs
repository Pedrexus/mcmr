use crate::graph::{EdgeKind, Graph, Node, NodeKind};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

use contracts::{Declaration, ParameterDeclaration};
use link::OverrideLink;

mod contracts;
mod link;

/// Pair every class with each class it inherits from, and state what meets across the link.
///
/// This is the evidence no syntax reader can produce, because the base is usually in another file
/// and finding it means resolving the inheritance chain across the repository. It is what the
/// Pylint override family needs, and the graph already holds both halves.
///
/// A member is attached to the nearest ancestor that declares it, so a name three classes deep is
/// compared against the declaration Python would actually reach rather than against every class
/// that ever mentioned it. A link with nothing crossing it is still emitted, because inheriting
/// from a sealed class is a defect the members say nothing about.
pub fn pairs(graph: &Graph) -> Vec<Value> {
    Inheritance::of(graph).facts()
}

/// Everything the graph knows about who inherits from whom and who declares what.
struct Inheritance<'a> {
    classes: BTreeMap<&'a str, &'a Node>,
    bases: BTreeMap<&'a str, Vec<&'a Node>>,
    members: BTreeMap<&'a str, Vec<Declaration>>,
    initializers: BTreeMap<&'a str, Vec<String>>,
}

/// Every parameter node one callable defines, keyed by the callable that defines it.
type Signatures<'a> = BTreeMap<&'a str, Vec<&'a Node>>;

impl<'a> Inheritance<'a> {
    /// Index one built graph into the four questions an override pair asks of it.
    fn of(graph: &'a Graph) -> Self {
        let nodes: BTreeMap<&str, &Node> = graph
            .nodes
            .iter()
            .map(|node| (node.id.as_str(), node))
            .collect();
        let classes: BTreeMap<&str, &Node> = nodes
            .iter()
            .filter(|(_, node)| node.kind == NodeKind::Class)
            .map(|(id, node)| (*id, *node))
            .collect();
        let mut signatures: Signatures = BTreeMap::new();
        let mut held: BTreeMap<&str, Vec<&Node>> = BTreeMap::new();
        let mut bases: BTreeMap<&str, Vec<&Node>> = BTreeMap::new();
        let mut called: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for edge in &graph.edges {
            let source = edge.source.as_str();
            let Some(target) = nodes.get(edge.target.as_str()).copied() else {
                continue;
            };
            match edge.kind {
                EdgeKind::Define if target.kind == NodeKind::Parameter => {
                    signatures.entry(source).or_default().push(target);
                }
                EdgeKind::Define if is_member(target.kind) && classes.contains_key(source) => {
                    held.entry(source).or_default().push(target);
                }
                EdgeKind::Inherit if classes.contains_key(source) => {
                    bases.entry(source).or_default().push(target);
                }
                EdgeKind::Call | EdgeKind::Instantiate => {
                    called.entry(source).or_default().push(&target.qualname);
                }
                _ => {}
            }
        }
        let members: BTreeMap<&str, Vec<Declaration>> = held
            .iter()
            .map(|(class, declared)| (*class, declarations(declared, &signatures)))
            .collect();
        let initializers = classes
            .keys()
            .map(|class| (*class, initializer_calls(held.get(class), &called)))
            .collect();
        Self {
            classes,
            bases,
            members,
            initializers,
        }
    }

    /// Return the name of every base anywhere above one class, including unresolved ones.
    ///
    /// A rule asking whether a class is abstract asks about `ABC` and `Protocol`, and neither is
    /// declared in the repository being read, so the unresolved half of the chain is exactly the
    /// half that answers it.
    fn ancestor_names(&self, class: &str) -> Vec<&str> {
        let mut named: BTreeSet<&str> = self.base_names(class).into_iter().collect();
        for (ancestor, _) in self.ancestry(class) {
            named.extend(self.base_names(&ancestor.id));
        }
        named.into_iter().collect()
    }

    /// Return every class one class inherits from, nearest first, with how far away each one is.
    ///
    /// The order is the left-to-right depth-first walk Python resolves a name through, and a name
    /// already seen is never visited twice, so a diamond names its shared ancestor once and a
    /// cycle in a mistyped hierarchy terminates instead of hanging.
    fn ancestry(&self, class: &str) -> Vec<(&'a Node, usize)> {
        let mut order = Vec::new();
        let mut seen: BTreeSet<&str> = BTreeSet::new();
        let mut pending: Vec<(&'a Node, usize)> = self
            .inherited_classes(class)
            .into_iter()
            .rev()
            .map(|base| (base, 1))
            .collect();
        while let Some((current, depth)) = pending.pop() {
            if !seen.insert(current.id.as_str()) {
                continue;
            }
            order.push((current, depth));
            for base in self.inherited_classes(&current.id).into_iter().rev() {
                pending.push((base, depth + 1));
            }
        }
        order
    }

    /// Return the plain name of every base one class names, which is how a reader says it.
    fn base_names(&self, class: &str) -> Vec<&str> {
        self.named_bases(class)
            .iter()
            .map(|base| tail(&base.qualname))
            .collect()
    }

    /// Return what one class writes down itself.
    fn declarations_of(&self, class: &str) -> &[Declaration] {
        self.members
            .get(class)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    /// State one link as the fact a rule reads.
    fn fact(&self, link: OverrideLink<'_>) -> Value {
        let overridden_member_count = link
            .declared
            .iter()
            .filter(|candidate| {
                link.inherited
                    .iter()
                    .any(|item| item.name == candidate.name)
            })
            .count();
        let path = link
            .derived
            .path
            .as_deref()
            .expect("a resolved derived class must state its source path");
        let line = link
            .derived
            .line
            .expect("a resolved derived class must state its source line");
        json!({
            "key": format!("override:{}:{}", link.derived.qualname, link.base.qualname),
            "span": {
                "path": path,
                "start_line": line,
                "end_line": line,
            },
            "language": link.derived.language,
            "derived": link.derived.qualname,
            "base": link.base.qualname,
            "depth": link.depth,
            "overridden_member_count": overridden_member_count,
            "derived_decorators": link.derived.decorators,
            "base_decorators": link.base.decorators,
            "base_names": self.base_names(&link.derived.id),
            "ancestor_names": self.ancestor_names(&link.derived.id),
            "declared": link.declared,
            "inherited": link.inherited,
            "initializer_calls": self.initializers.get(link.derived.id.as_str()),
        })
    }

    /// Return one fact for every link between a class and a class it inherits from.
    fn facts(&self) -> Vec<Value> {
        let mut built = Vec::new();
        for (id, derived) in &self.classes {
            let declared = self.declarations_of(id).to_vec();
            let mut claimed: BTreeSet<&str> = BTreeSet::new();
            for (base, depth) in self.ancestry(id) {
                let inherited: Vec<Declaration> = self
                    .declarations_of(&base.id)
                    .iter()
                    .filter(|item| claimed.insert(item.name.as_str()))
                    .cloned()
                    .collect();
                built.push(self.fact(OverrideLink {
                    derived,
                    base,
                    depth,
                    declared: &declared,
                    inherited: &inherited,
                }));
            }
        }
        built
    }

    /// Return the classes one class names as a base, skipping what this repository cannot resolve.
    fn inherited_classes(&self, class: &str) -> Vec<&'a Node> {
        self.named_bases(class)
            .iter()
            .copied()
            .filter(|base| base.kind == NodeKind::Class)
            .collect()
    }

    /// Return every base one class names, resolved or not, in the order the class states them.
    fn named_bases(&self, class: &str) -> &[&'a Node] {
        self.bases.get(class).map(Vec::as_slice).unwrap_or_default()
    }
}

/// Return what one class writes down, keeping the callable when a name is also written as data.
///
/// A class holding both `def run` and `self.run` states two nodes under one name, and the
/// declaration a reader meets in the class body is the callable one.
fn declarations(held: &[&Node], signatures: &Signatures) -> Vec<Declaration> {
    let mut by_name: BTreeMap<String, Declaration> = BTreeMap::new();
    for node in held {
        let stated = declaration(node, signatures);
        if by_name
            .get(&stated.name)
            .is_some_and(|kept| kept.parameters.is_some())
        {
            continue;
        }
        by_name.insert(stated.name.clone(), stated);
    }
    by_name.into_values().collect()
}

/// Return one member exactly as its own declaration reads.
///
/// Every parameter reaches this join through the graph's parameter constructor, which requires
/// both its ordinal and binding kind. Missing metadata is therefore a provider defect rather than
/// an ordinary parameter this pass can safely invent.
fn declaration(node: &Node, signatures: &Signatures) -> Declaration {
    let parameters = (node.kind != NodeKind::Attribute).then(|| {
        let mut stated = signatures
            .get(node.id.as_str())
            .cloned()
            .unwrap_or_default();
        stated.sort_by_key(|held| {
            held.ordinal
                .expect("a declared parameter must state its ordinal")
        });
        stated
            .into_iter()
            .map(|held| ParameterDeclaration {
                name: tail(&held.qualname).to_string(),
                kind: held
                    .parameter_kind
                    .expect("a declared parameter must state its binding kind"),
                has_default: held.has_default,
            })
            .collect()
    });
    Declaration {
        name: tail(&node.qualname).to_string(),
        parameters,
        decorators: node.decorators.clone(),
        asynchronous: node.asynchronous,
        line: node
            .line
            .expect("a declared class member must state its source line"),
        source: node.source.clone().unwrap_or_default(),
    }
}

/// Return whose initializer one class invokes from its own initializer.
///
/// Both shapes a reader writes arrive here. `super().__init__()` leaves an unresolved reference
/// naming the expression as written, and `Base.__init__(self)` resolves to the method itself, so
/// stripping the member and keeping the receiver states them the same way.
fn initializer_calls(
    held: Option<&Vec<&Node>>,
    called: &BTreeMap<&str, Vec<&str>>,
) -> Vec<String> {
    held.map(Vec::as_slice)
        .unwrap_or_default()
        .iter()
        .filter(|node| tail(&node.qualname) == "__init__")
        .flat_map(|node| {
            called
                .get(node.id.as_str())
                .map(Vec::as_slice)
                .unwrap_or_default()
        })
        .filter_map(|qualname| receiver(qualname))
        .collect()
}

/// Return who one initializer call is made on, when the call is on an initializer at all.
fn receiver(qualname: &str) -> Option<String> {
    let holder = qualname.strip_suffix(".__init__")?;
    let named = tail(holder);
    Some(named.split('(').next().unwrap_or(named).to_string())
}

/// Whether one node is something a class holds rather than something it merely mentions.
fn is_member(kind: NodeKind) -> bool {
    matches!(
        kind,
        NodeKind::Method | NodeKind::Property | NodeKind::Attribute
    )
}

/// Return the last step of one qualified name, in either separator a language writes.
fn tail(qualname: &str) -> &str {
    qualname.rsplit(['.', ':']).next().unwrap_or(qualname)
}

#[cfg(test)]
mod tests;
