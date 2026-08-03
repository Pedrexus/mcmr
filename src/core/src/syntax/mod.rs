use crate::source::Source;
use crate::walk::qualified_name;
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

mod fact_identity;
mod node_value;
mod packing;
mod record;

pub use fact_identity::SyntaxFactIdentity;
use node_value::SyntaxNodeValue;
use packing::pack;
#[cfg(test)]
pub use packing::unpack;
pub use record::{PackedSyntaxRecord, SyntaxRecord};

/// The whole vocabulary a syntax tree may use, whichever language filled it.
///
/// Every frontend maps its own grammar onto this list and nothing else. A rule reading a tree can
/// then be written once, and a frontend that invents a kind of its own is caught by the test that
/// checks what it emits against this, rather than by a rule quietly never matching.
pub const KINDS: &[&str] = &[
    "callable",
    "type",
    "binding",
    "branch",
    "loop",
    "guard",
    "scope",
    "return",
    "raise",
    "import",
    "effect",
    "statement",
    "call",
    "name",
    "member",
    "text",
    "literal",
    "collection",
    "comprehension",
    "operation",
    "index",
    "await",
    "expression",
];

/// Return one kind if the shared vocabulary holds it, and the neutral kind if it does not.
///
/// A frontend cannot invent a kind by accident, because inventing one lands here and comes back
/// as `expression`. A rule matching on the vocabulary therefore never silently fails to match
/// something a new language decided to call by another name.
pub fn known(kind: &str) -> &str {
    match KINDS.contains(&kind) {
        true => kind,
        false => "expression",
    }
}

/// Assemble one declaration's fact in the shape every frontend produces it.
pub fn fact(source: &Source, identity: SyntaxFactIdentity<'_>, tree: Value) -> Value {
    let location = tree["span"].clone();
    let start_line = location["start_line"].as_u64().unwrap_or(1);
    let start_column = location["start_column"].as_u64().unwrap_or(0);
    json!({
        "key": format!("syntax:{}:{start_line}:{start_column}:{}", source.relative, identity.qualname),
        "span": location,
        "language": identity.language,
        "qualname": identity.qualname,
        "kind": tree["kind"],
        "source": identity.written,
        "nodes": pack(tree),
    })
}

/// What one node in a declaration's own tree is, in terms every language shares.
///
/// This is deliberately not a parse tree. A rule reading it wants to ask what a function binds,
/// what it calls, and what it writes down, and a faithful tree buries all three under the syntax
/// each language happens to use. Twelve kinds carry those questions, and anything a language adds
/// beyond them arrives as its children rather than as a kind nobody else has.
fn kind_of(statement: &Stmt) -> &'static str {
    match statement {
        Stmt::FunctionDef(_) => "callable",
        Stmt::ClassDef(_) => "type",
        Stmt::Return(_) => "return",
        Stmt::Assign(_) | Stmt::AnnAssign(_) | Stmt::AugAssign(_) => "binding",
        Stmt::If(_) => "branch",
        Stmt::For(_) | Stmt::While(_) => "loop",
        Stmt::Try(_) => "guard",
        Stmt::With(_) => "scope",
        Stmt::Raise(_) => "raise",
        Stmt::Import(_) | Stmt::ImportFrom(_) => "import",
        Stmt::Expr(_) => "effect",
        _ => "statement",
    }
}

fn expression_kind(expression: &Expr) -> &'static str {
    match expression {
        Expr::Call(_) => "call",
        Expr::Name(_) => "name",
        Expr::Attribute(_) => "member",
        Expr::StringLiteral(_) | Expr::FString(_) => "text",
        Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::NoneLiteral(_) => "literal",
        Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) | Expr::Dict(_) => "collection",
        Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
            "comprehension"
        }
        Expr::Lambda(_) => "callable",
        Expr::Compare(_) | Expr::BoolOp(_) | Expr::UnaryOp(_) | Expr::BinOp(_) => "operation",
        Expr::Subscript(_) => "index",
        Expr::Await(_) => "await",
        _ => "expression",
    }
}

/// Return the name one piece of syntax states, when it states one.
///
/// A rule about naming needs the identifier itself rather than the source that surrounds it, and
/// pulling it out here is what keeps every such rule from re-parsing the text it was handed.
fn named(expression: &Expr) -> String {
    match expression {
        Expr::Name(item) => item.id.to_string(),
        Expr::Attribute(item) => item.attr.to_string(),
        Expr::Call(item) => qualified_name(&item.func),
        _ => String::new(),
    }
}

fn statement_name(statement: &Stmt) -> String {
    match statement {
        Stmt::FunctionDef(item) => item.name.to_string(),
        Stmt::ClassDef(item) => item.name.to_string(),
        Stmt::Assign(item) => item.targets.first().map(named).unwrap_or_default(),
        Stmt::AnnAssign(item) => named(&item.target),
        Stmt::AugAssign(item) => named(&item.target),
        Stmt::For(item) => named(&item.target),
        _ => String::new(),
    }
}

/// Build the complete semantic tree one declaration states.
fn tree(source: &Source, statement: &Stmt) -> Value {
    let mut children: Vec<(u32, Value)> = Vec::new();
    for expression in crate::walk::expressions(statement) {
        let offset = expression.range().start().into();
        children.push((offset, expression_tree(source, expression)));
    }
    for block in crate::walk::blocks(statement) {
        for held in block {
            // A nested declaration carries its own fact, so its body stops here. Walking into it
            // would count every defect inside a method twice.
            let nested = matches!(held, Stmt::FunctionDef(_) | Stmt::ClassDef(_));
            let held_tree = match nested {
                true => node(
                    source,
                    SyntaxNodeValue {
                        kind: kind_of(held),
                        name: &statement_name(held),
                        range: held.range(),
                        children: Vec::new(),
                    },
                ),
                false => tree(source, held),
            };
            children.push((held.range().start().into(), held_tree));
        }
    }
    // Children read in source order, because a rule about code reads the code in that order.
    children.sort_by_key(|(offset, _)| *offset);
    node(
        source,
        SyntaxNodeValue {
            kind: kind_of(statement),
            name: &statement_name(statement),
            range: statement.range(),
            children: children.into_iter().map(|(_, held)| held).collect(),
        },
    )
}

fn expression_tree(source: &Source, expression: &Expr) -> Value {
    let children = crate::walk::children(expression)
        .into_iter()
        .map(|child| expression_tree(source, child))
        .collect();
    node(
        source,
        SyntaxNodeValue {
            kind: expression_kind(expression),
            name: &named(expression),
            range: expression.range(),
            children,
        },
    )
}

fn node(source: &Source, node: SyntaxNodeValue<'_>) -> Value {
    json!({
        "kind": known(node.kind),
        "name": node.name,
        "span": source.span(node.range),
        "children": node.children,
    })
}

/// Every declaration one module states, each with the tree and the source it spans.
///
/// One fact per declaration rather than one per module, because a rule about a function wants that
/// function. Asking for this family is how a rule says it needs to read code rather than counts,
/// and a rule that never asks never pays for the tree.
pub fn declarations(source: &Source, module: &ModModule) -> Vec<Value> {
    let mut facts = Vec::new();
    collect(source, &module.body, "", &mut facts);
    facts
}

fn collect(source: &Source, body: &[Stmt], owner: &str, facts: &mut Vec<Value>) {
    for statement in body {
        let name = statement_name(statement);
        let qualname = match owner.is_empty() {
            true => name.clone(),
            false => format!("{owner}.{name}"),
        };
        if matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            facts.push(fact(
                source,
                SyntaxFactIdentity {
                    language: "python",
                    qualname: &qualname,
                    written: source.slice(statement.range()),
                },
                tree(source, statement),
            ));
        }
        for block in crate::walk::blocks(statement) {
            collect(source, block, &qualname, facts);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ruff_python_parser::parse_module;

    fn declarations_of(text: &str) -> Vec<Value> {
        let document = crate::discovery::Document {
            relative: "src/example.py".to_string(),
            source: text.to_string(),
        };
        let source = Source::new(&document);
        let parsed = parse_module(text).expect("the fixture parses");
        declarations(&source, parsed.syntax())
    }

    #[test]
    fn a_declaration_carries_its_own_source_and_its_own_tree() {
        let facts = declarations_of(
            "def rename(name: str) -> str:\n    bare = name.lstrip('_')\n    return f'is_{bare}'\n",
        );

        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0]["qualname"], "rename");
        assert_eq!(facts[0]["kind"], "callable");
        assert!(
            facts[0]["source"]
                .as_str()
                .unwrap_or_default()
                .starts_with("def rename")
        );
        let tree = unpack(&facts[0]);
        let body = tree["children"].as_array().unwrap();
        let kinds: Vec<&str> = body
            .iter()
            .map(|item| item["kind"].as_str().unwrap_or_default())
            .collect();
        // The signature's own names come first, then the body, in the order the source states.
        assert_eq!(kinds, vec!["name", "name", "binding", "return"]);
        assert_eq!(body[2]["name"], "bare");
        assert!(tree.get("text").is_none());
        assert!(body.iter().all(|node| node.get("text").is_none()));
    }

    #[test]
    fn a_class_tree_stops_at_the_methods_that_carry_their_own_facts() {
        let facts = declarations_of(
            "class Engine:\n    def run(self):\n        total = 0\n        return total\n",
        );
        let held = unpack(&facts[0]);
        let method = unpack(&facts[1]);

        assert_eq!(facts[0]["qualname"], "Engine");
        assert_eq!(held["children"][0]["kind"], "callable");
        assert!(
            held["children"][0]["children"]
                .as_array()
                .unwrap()
                .is_empty(),
            "a method body inside a class tree would count every defect in it twice"
        );
        let body: Vec<&str> = method["children"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| item["name"].as_str().unwrap_or_default())
            .collect();
        assert!(
            body.contains(&"total"),
            "the method keeps its own body, {body:?}"
        );
    }

    #[test]
    fn a_nested_declaration_is_named_by_what_holds_it() {
        let facts =
            declarations_of("class Engine:\n    def run(self) -> int:\n        return 1\n");

        assert_eq!(
            facts
                .iter()
                .map(|fact| fact["qualname"].as_str().unwrap_or_default())
                .collect::<Vec<_>>(),
            vec!["Engine", "Engine.run"]
        );
    }

    #[test]
    fn the_tree_reaches_the_names_and_the_calls_a_body_states() {
        let facts = declarations_of("def run(values):\n    return sorted(values.keys())\n");
        let mut kinds = Vec::new();
        let tree = unpack(&facts[0]);
        let mut pending = vec![&tree];
        while let Some(node) = pending.pop() {
            kinds.push((
                node["kind"].as_str().unwrap_or_default().to_string(),
                node["name"].as_str().unwrap_or_default().to_string(),
            ));
            pending.extend(node["children"].as_array().into_iter().flatten());
        }

        assert!(kinds.contains(&("call".to_string(), "sorted".to_string())));
        assert!(kinds.contains(&("member".to_string(), "keys".to_string())));
        assert!(kinds.contains(&("name".to_string(), "values".to_string())));
    }

    /// Return every kind one tree uses, so a frontend cannot invent one quietly.
    pub fn kinds_used(tree: &Value) -> std::collections::BTreeSet<String> {
        let mut found = std::collections::BTreeSet::new();
        let mut pending = vec![tree];
        while let Some(node) = pending.pop() {
            if let Some(kind) = node["kind"].as_str() {
                found.insert(kind.to_string());
            }
            pending.extend(node["children"].as_array().into_iter().flatten());
        }
        found
    }

    #[test]
    fn every_kind_a_tree_uses_is_in_the_shared_vocabulary() {
        let facts = declarations_of(
            "class Engine:\n    def run(self, values):\n        found = [v for v in values if v]\n        try:\n            return sorted(found)[0]\n        except IndexError:\n            raise ValueError('empty')\n",
        );
        let known: std::collections::BTreeSet<&str> = KINDS.iter().copied().collect();

        for fact in &facts {
            for kind in kinds_used(&unpack(fact)) {
                assert!(
                    known.contains(kind.as_str()),
                    "{kind} is not in the vocabulary"
                );
            }
        }
    }

    #[test]
    fn a_deep_expression_reaches_the_tree_without_a_private_ceiling() {
        let document = crate::discovery::Document {
            relative: "src/example.py".to_string(),
            source: "def run():\n    return one(two(three(four(five(six(seven(eight())))))))\n"
                .to_string(),
        };
        let source = Source::new(&document);
        let parsed = parse_module(&source.text).expect("the fixture parses");

        let facts = declarations(&source, parsed.syntax());
        let mut names = Vec::new();
        let tree = unpack(&facts[0]);
        let mut pending = vec![&tree];
        while let Some(node) = pending.pop() {
            names.push(node["name"].as_str().unwrap_or_default());
            pending.extend(node["children"].as_array().into_iter().flatten());
        }

        assert!(names.contains(&"eight"));
    }
}
