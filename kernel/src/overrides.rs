use crate::graph::{EdgeKind, Graph, Node, NodeKind, ParameterKind};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// One parameter of one declaration, as the language holding it binds an argument to it.
///
/// Comparing two signatures is a question about positions a caller has to fill and names a caller
/// may pass, so a bare list of names cannot answer it. A parameter that carries a default is one
/// the caller may leave out, and a parameter that swallows a tail stands for every argument the
/// base ever accepted.
#[derive(Clone, Debug, Serialize)]
pub struct ParameterDeclaration {
    pub name: String,
    pub kind: ParameterKind,
    pub has_default: bool,
}

/// How one class writes down one member, exactly as its own declaration reads.
///
/// A callable carries its parameters in the order it states them, and data carries no parameter
/// list at all. That is what lets a reader tell a method from an attribute wearing the same name,
/// which is the whole of one Pylint message and half of three others.
#[derive(Clone, Debug, Serialize)]
pub struct Declaration {
    pub name: String,
    pub parameters: Option<Vec<ParameterDeclaration>>,
    pub decorators: Vec<String>,
    pub asynchronous: bool,
    pub line: usize,
}

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
                built.push(self.fact(derived, base, depth, &declared, &inherited));
            }
        }
        built
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

    /// Return what one class writes down itself.
    fn declarations_of(&self, class: &str) -> &[Declaration] {
        self.members
            .get(class)
            .map(Vec::as_slice)
            .unwrap_or_default()
    }

    /// Return the plain name of every base one class names, which is how a reader says it.
    fn base_names(&self, class: &str) -> Vec<&str> {
        self.named_bases(class)
            .iter()
            .map(|base| tail(&base.qualname))
            .collect()
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

    /// State one link as the fact a rule reads.
    fn fact(
        &self,
        derived: &Node,
        base: &Node,
        depth: usize,
        declared: &[Declaration],
        inherited: &[Declaration],
    ) -> Value {
        let line = derived.line.unwrap_or(1);
        json!({
            "key": format!("override:{}:{}", derived.qualname, base.qualname),
            "span": {
                "path": derived.path.clone().unwrap_or_default(),
                "start_line": line,
                "end_line": line,
            },
            "language": derived.language,
            "derived": derived.qualname,
            "base": base.qualname,
            "depth": depth,
            "derived_decorators": derived.decorators,
            "base_decorators": base.decorators,
            "base_names": self.base_names(&derived.id),
            "ancestor_names": self.ancestor_names(&derived.id),
            "declared": declared,
            "inherited": inherited,
            "initializer_calls": self.initializers.get(derived.id.as_str()),
        })
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
/// A parameter whose frontend stated no kind is read as the ordinary one, which binds by position
/// and answers to its own name too. That reading invents neither a keyword a language does not
/// have nor a variadic tail nothing wrote.
fn declaration(node: &Node, signatures: &Signatures) -> Declaration {
    let parameters = (node.kind != NodeKind::Attribute).then(|| {
        let mut stated = signatures
            .get(node.id.as_str())
            .cloned()
            .unwrap_or_default();
        stated.sort_by_key(|held| held.ordinal.unwrap_or(0));
        stated
            .into_iter()
            .map(|held| ParameterDeclaration {
                name: tail(&held.qualname).to_string(),
                kind: held
                    .parameter_kind
                    .unwrap_or(ParameterKind::PositionalOrKeyword),
                has_default: held.has_default,
            })
            .collect()
    });
    Declaration {
        name: tail(&node.qualname).to_string(),
        parameters,
        decorators: node.decorators.clone(),
        asynchronous: node.asynchronous,
        line: node.line.unwrap_or(1),
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
mod tests {
    use super::*;
    use crate::discovery::Document;

    fn facts_of(source: &str) -> Vec<Value> {
        let graph = crate::graph::build(
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
        );
        pairs(&graph)
    }

    fn link<'a>(facts: &'a [Value], derived: &str, base: &str) -> &'a Value {
        facts
            .iter()
            .find(|fact| {
                fact["derived"]
                    .as_str()
                    .is_some_and(|name| name.ends_with(derived))
                    && fact["base"]
                        .as_str()
                        .is_some_and(|name| name.ends_with(base))
            })
            .expect("the link is missing")
    }

    fn names(fact: &Value, side: &str) -> Vec<String> {
        fact[side]
            .as_array()
            .expect("a declaration list")
            .iter()
            .map(|item| item["name"].as_str().unwrap_or_default().to_string())
            .collect()
    }

    #[test]
    fn a_link_carries_both_declarations_of_the_member_that_crosses_it() {
        let facts = facts_of(
            "class Base:\n    def run(self, count):\n        return count\n\n\nclass Engine(Base):\n    def run(self, total):\n        return total\n",
        );
        let found = link(&facts, "Engine", "Base");

        assert_eq!(facts.len(), 1);
        assert_eq!(found["depth"], 1);
        assert_eq!(names(found, "inherited"), ["run"]);
        assert_eq!(found["inherited"][0]["parameters"][1]["name"], "count");
        assert_eq!(found["declared"][0]["parameters"][1]["name"], "total");
        assert_eq!(found["base_names"][0], "Base");
    }

    #[test]
    fn a_parameter_states_how_it_binds_and_whether_a_caller_may_leave_it_out() {
        let facts = facts_of(
            "class Base:\n    def run(self, first, /, second, *rest, flag=True, **extra):\n        return first\n\n\nclass Engine(Base):\n    def run(self, first, /, second, *rest, flag=True, **extra):\n        return second\n",
        );
        let stated = &link(&facts, "Engine", "Base")["inherited"][0]["parameters"];
        let kinds: Vec<&str> = stated
            .as_array()
            .expect("a parameter list")
            .iter()
            .filter_map(|item| item["kind"].as_str())
            .collect();

        assert_eq!(
            kinds,
            [
                "positional_only",
                "positional_only",
                "positional_or_keyword",
                "var_positional",
                "keyword_only",
                "var_keyword",
            ]
        );
        assert_eq!(stated[4]["name"], "flag");
        assert_eq!(stated[4]["has_default"], true);
        assert_eq!(stated[2]["has_default"], false);
    }

    #[test]
    fn the_nearest_ancestor_owns_a_member_every_class_above_declares() {
        let facts = facts_of(
            "class Root:\n    def run(self):\n        return 1\n\n\nclass Middle(Root):\n    def run(self):\n        return 2\n\n\nclass Leaf(Middle):\n    def run(self):\n        return 3\n",
        );

        assert_eq!(names(link(&facts, "Leaf", "Middle"), "inherited"), ["run"]);
        assert!(names(link(&facts, "Leaf", "Root"), "inherited").is_empty());
        assert_eq!(link(&facts, "Leaf", "Root")["depth"], 2);
    }

    #[test]
    fn a_decorator_and_an_await_travel_with_the_half_that_wrote_them() {
        let facts = facts_of(
            "from typing import final\n\n\nclass Base:\n    @property\n    def size(self):\n        return 1\n\n    @final\n    async def fetch(self):\n        return 2\n\n\nclass Engine(Base):\n    def size(self):\n        return 3\n\n    def fetch(self):\n        return 4\n",
        );
        let found = link(&facts, "Engine", "Base");

        assert_eq!(found["inherited"][0]["name"], "fetch");
        assert_eq!(found["inherited"][0]["decorators"][0], "final");
        assert_eq!(found["inherited"][0]["asynchronous"], true);
        assert_eq!(found["inherited"][1]["decorators"][0], "property");
        assert_eq!(found["declared"][0]["asynchronous"], false);
    }

    #[test]
    fn an_attribute_and_a_method_are_told_apart_by_the_parameters_only_one_has() {
        let facts = facts_of(
            "class Base:\n    def __init__(self):\n        self.run = None\n\n\nclass Engine(Base):\n    def run(self):\n        return 1\n",
        );
        let found = link(&facts, "Engine", "Base");
        let hidden = found["inherited"]
            .as_array()
            .expect("declarations")
            .iter()
            .find(|item| item["name"] == "run")
            .expect("the attribute");

        assert!(hidden["parameters"].is_null());
        assert_eq!(found["declared"][0]["parameters"][0]["name"], "self");
    }

    #[test]
    fn an_initializer_states_whose_initializer_it_called() {
        let facts = facts_of(
            "class Base:\n    def __init__(self):\n        self.total = 0\n\n\nclass Other:\n    def __init__(self):\n        self.count = 0\n\n\nclass Polite(Base):\n    def __init__(self):\n        super().__init__()\n\n\nclass Rude(Base):\n    def __init__(self):\n        Other.__init__(self)\n\n\nclass Silent(Base):\n    def __init__(self):\n        self.total = 1\n",
        );

        assert_eq!(
            link(&facts, "Polite", "Base")["initializer_calls"][0],
            "super"
        );
        assert_eq!(
            link(&facts, "Rude", "Base")["initializer_calls"][0],
            "Other"
        );
        assert!(
            link(&facts, "Silent", "Base")["initializer_calls"]
                .as_array()
                .expect("a call list")
                .is_empty()
        );
    }

    #[test]
    fn an_unresolved_base_is_named_without_pretending_to_be_a_link() {
        let facts = facts_of(
            "from abc import ABC, abstractmethod\n\n\nclass Base(ABC):\n    @abstractmethod\n    def run(self):\n        return 1\n\n\nclass Engine(Base):\n    def other(self):\n        return 2\n",
        );
        let found = link(&facts, "Engine", "Base");
        let ancestors: Vec<&str> = found["ancestor_names"]
            .as_array()
            .expect("names")
            .iter()
            .filter_map(Value::as_str)
            .collect();

        assert_eq!(facts.len(), 1);
        assert_eq!(found["base_names"][0], "Base");
        assert!(ancestors.contains(&"ABC"));
        assert_eq!(found["inherited"][0]["decorators"][0], "abstractmethod");
    }

    #[test]
    fn a_class_nothing_in_this_repository_is_above_produces_no_link() {
        assert!(facts_of("class Alone:\n    def run(self):\n        return 1\n").is_empty());
    }
}
