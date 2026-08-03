use super::super::support::{
    QualifiedNativeName, child, children, descendant, dialect, is_declaration, is_name,
    is_transparent, is_type, kind_of, located, named_by,
};
use super::Unit;
use serde_json::{Value, json};
use tree_sitter::Node as Syntax;

#[derive(Clone, Copy)]
struct SyntaxDeclaration<'a> {
    qualname: &'a str,
    kind: &'a str,
}

impl Unit {
    /// Every declaration this translation unit states, each with its source and its tree.
    ///
    /// The kinds are the shared vocabulary rather than this grammar's own, so a rule written
    /// against a Python declaration reads a C++ one without learning what a
    /// `field_declaration_list` is. A namespace and a type qualify what they hold, which is what
    /// makes a method named for the type that declares it.
    pub(in crate::native) fn syntax_facts(&self, root: Syntax) -> Vec<Value> {
        let mut facts = Vec::new();
        self.declared(root, "", &mut facts);
        facts
    }

    fn declared(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        for held in children(node) {
            self.declare_node(held, owner, facts);
        }
    }

    fn declare_node(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        if is_type(node) {
            self.declare_type(node, owner, facts);
            return;
        }
        match node.kind() {
            "function_definition" => self.declare_callable(node, owner, facts),
            "namespace_definition" => self.declare_namespace(node, owner, facts),
            "linkage_specification"
            | "template_declaration"
            | "declaration_list"
            | "field_declaration_list"
            | "preproc_ifdef"
            | "preproc_if" => self.declared(node, owner, facts),
            _ => {}
        }
    }

    fn declare_type(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        let Some(named) = child(node, "type_identifier") else {
            return;
        };
        let qualname = QualifiedNativeName::new(owner).with(self.text(named));
        facts.push(self.declaration(
            node,
            SyntaxDeclaration {
                qualname: &qualname,
                kind: "type",
            },
        ));
        if let Some(body) = descendant(node, "field_declaration_list") {
            self.declared(body, &qualname, facts);
        }
    }

    fn declare_callable(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        if let Some(named) = self.declared_name(node) {
            let qualname = QualifiedNativeName::new(owner).with(&named);
            facts.push(self.declaration(
                node,
                SyntaxDeclaration {
                    qualname: &qualname,
                    kind: "callable",
                },
            ));
        }
    }

    fn declare_namespace(&self, node: Syntax, owner: &str, facts: &mut Vec<Value>) {
        let named = node
            .child_by_field_name("name")
            .map(|name| self.text(name).to_string())
            .unwrap_or_default();
        if let Some(body) = node.child_by_field_name("body") {
            self.declared(body, &QualifiedNativeName::new(owner).with(&named), facts);
        }
    }

    fn declaration(&self, node: Syntax, declaration: SyntaxDeclaration<'_>) -> Value {
        let tree = json!({
            "kind": crate::syntax::known(declaration.kind),
            "name": declaration.qualname.rsplit("::").next().unwrap_or(declaration.qualname),
            "span": self.locate(node),
            "children": self.contents(node),
        });
        crate::syntax::fact(
            &self.source,
            crate::syntax::SyntaxFactIdentity {
                language: dialect(self.language),
                qualname: declaration.qualname,
                written: self.text(node),
            },
            tree,
        )
    }

    /// Return what one declaration holds, which is the type it states and the body it opens.
    ///
    /// Parameters are deliberately left out. Every frontend carries them in `FunctionFact`
    /// already, and no other one puts them in the tree, so listing them here would make a rule
    /// about local names answer differently for this language than for any other.
    fn contents(&self, node: Syntax) -> Vec<Value> {
        let mut found: Vec<Value> = node
            .child_by_field_name("type")
            .filter(|stated| !is_type(*stated))
            .map(|stated| self.leaf(stated))
            .into_iter()
            .collect();
        if let Some(body) = node.child_by_field_name("body") {
            found.extend(self.spliced(body));
        }
        found
    }

    fn branch(&self, node: Syntax, children: Vec<Value>) -> Value {
        let location = located(node);
        json!({
            "kind": crate::syntax::known(kind_of(node)),
            "name": self.stated_name(node),
            "span": self.locate(location),
            "children": children,
        })
    }

    fn leaf(&self, node: Syntax) -> Value {
        self.branch(node, Vec::new())
    }

    fn expanded(&self, node: Syntax) -> Value {
        self.branch(node, self.spliced(node))
    }

    /// Return the nodes one node contributes, walking through the wrappers that carry no meaning.
    fn spliced(&self, node: Syntax) -> Vec<Value> {
        let restated = named_by(node);
        let mut found = Vec::new();
        for held in children(node) {
            if held.kind() == "comment" {
                // A comment sits anywhere a token does and the grammar hands it over as a child.
                // It is what the comment family reads, and code is what this tree states.
                continue;
            }
            if is_transparent(held) {
                found.extend(self.spliced(held));
            } else if restated == Some(held) {
                continue;
            } else if is_declaration(held) {
                // A nested declaration carries its own fact, so its body stops here. Walking into
                // it would count every defect inside a method twice, once for the method and
                // again for the type that holds it.
                found.push(self.leaf(held));
            } else {
                found.push(self.expanded(held));
            }
        }
        found
    }

    /// Return the name one piece of syntax states, when it states one.
    fn stated_name(&self, node: Syntax) -> String {
        if is_type(node) || is_name(node) {
            return child(node, "type_identifier")
                .map(|named| self.text(named))
                .unwrap_or_else(|| self.text(node))
                .to_string();
        }
        match node.kind() {
            "function_definition"
            | "declaration"
            | "field_declaration"
            | "parameter_declaration"
            | "init_declarator" => self
                .declared_name(node)
                .or_else(|| self.declarator_name(node.child_by_field_name("declarator")?))
                .unwrap_or_default(),
            "call_expression" | "new_expression" => node
                .child_by_field_name("function")
                .or_else(|| node.child_by_field_name("type"))
                .map(|function| self.callee(function))
                .unwrap_or_default(),
            "field_expression" => node
                .child_by_field_name("field")
                .map(|field| self.text(field).to_string())
                .unwrap_or_default(),
            "assignment_expression" | "expression_statement" => self.assigned(node),
            "primitive_type" | "sized_type_specifier" | "namespace_identifier" => {
                self.text(node).to_string()
            }
            _ => String::new(),
        }
    }

    /// Return the name one statement assigns to, looking through the statement that wraps it.
    fn assigned(&self, node: Syntax) -> String {
        let stated = match node.kind() {
            "expression_statement" => child(node, "assignment_expression"),
            _ => Some(node),
        };
        stated
            .and_then(|held| held.child_by_field_name("left"))
            .map(|left| self.text(left).to_string())
            .unwrap_or_default()
    }
}
