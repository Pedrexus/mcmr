use super::super::support::{
    binding_level, child, children, control_increments, descendant, dialect, enclosing_type,
    executable_children, in_anonymous_namespace, is_name, is_type, native_parameter, visibility,
    walk, wrapped,
};
use super::Unit;
use crate::comments;
use crate::functions::{FunctionParameter, FunctionRecord};
use crate::graph::Visibility;
use crate::protocol::JsonObject;
use serde_json::{Value, json};
use tree_sitter::Node as Syntax;

mod member_position;
mod type_body;

use member_position::MemberPosition;
use type_body::TypeBody;

#[derive(Clone, Copy)]
struct DeclaratorLevel<'a> {
    level: Syntax<'a>,
    bound: Syntax<'a>,
}

impl Unit {
    pub fn function_facts(&self, root: Syntax) -> Vec<FunctionRecord> {
        walk(root)
            .into_iter()
            .filter(|node| node.kind() == "function_definition")
            .filter_map(|node| {
                let declarator = node.child_by_field_name("declarator")?;
                let name = self.declarator_name(declarator)?;
                let held = enclosing_type(node).is_some() || name.contains("::");
                let body = node.child_by_field_name("body");
                let statements = body.map(executable_children).unwrap_or_default();
                let increments = body.map(control_increments).unwrap_or_default();
                let range = comments::at(node.start_byte()..node.end_byte());
                let mut fact =
                    FunctionRecord::new(self.source.span(range), dialect(self.language), name);
                fact.identity.scope = if held { "method" } else { "module" }.to_string();
                fact.presentation.visibility = visibility(self.reach(node)).to_string();
                fact.semantics.roles.is_async = body.is_some_and(|body| {
                    walk(body).iter().any(|held| {
                        matches!(held.kind(), "co_await_expression" | "co_yield_statement")
                    })
                });
                fact.structure.implementation_lines = statements
                    .first()
                    .zip(statements.last())
                    .map_or(0, |(first, last)| {
                        last.end_position().row - first.start_position().row + 1
                    });
                fact.structure.direct_statement_count = statements.len();
                fact.measures.conditional_count = increments
                    .iter()
                    .filter(|increment| increment.kind == "conditional")
                    .count();
                fact.structure.control_increments = increments;
                fact.structure.parameters = self.parameters(declarator);
                fact.presentation.nodes.definition = Some(self.source.node("function", range));
                Some(fact)
            })
            .collect()
    }

    /// Return every position one signature declares, in the order a caller fills them.
    ///
    /// A position a caller may leave out is still a position, so the list holds it and says a
    /// caller need not fill it. Dropping it instead would close the gap between two parameters
    /// that are not adjacent and make a rule about transposable neighbours compare a pair no
    /// caller ever writes side by side.
    fn parameters(&self, declarator: Syntax) -> Vec<FunctionParameter> {
        let Some(list) = descendant(declarator, "parameter_list") else {
            return Vec::new();
        };
        children(list)
            .into_iter()
            .filter_map(native_parameter)
            .map(|(node, _, has_default)| {
                let type_name = self.declared_type(node);
                let has_boolean_annotation =
                    matches!(type_name.as_str(), "bool" | "_Bool" | "BOOL");
                let name = node
                    .child_by_field_name("declarator")
                    .and_then(|inner| self.declarator_name(inner))
                    .unwrap_or_default();
                let mut fact = FunctionParameter::named(name);
                fact.type_name = type_name;
                fact.contract.is_positional_only = true;
                fact.contract.is_required_by_external_contract = !has_default;
                fact.contract.has_boolean_annotation = has_boolean_annotation;
                fact
            })
            .collect()
    }

    /// Return the type one parameter declares, as the caller filling that position sees it.
    ///
    /// Half of a type in this language sits in the declarator rather than in the type the
    /// declaration names, so `int32_t *__restrict__ tokens` and `int32_t seg_start` write the same
    /// word and share no type at all. Reading the named type alone makes a rule about
    /// interchangeable positions report a pointer beside a value, which no caller could transpose
    /// and no compiler would accept.
    ///
    /// A qualifier written at the level that binds the name is the one a caller never sees. `int
    /// *const` and `int *` accept the same argument, a by-value `const int` is an undertaking by
    /// the body rather than a demand on the caller, and `__restrict__` promises the callee
    /// something about aliasing. Every other qualifier reaches the value being handed over, so
    /// `const int32_t *` stays apart from `int32_t *` the way a compiler keeps them apart.
    fn declared_type(&self, node: Syntax) -> String {
        let Some(stated) = node.child_by_field_name("type") else {
            return String::new();
        };
        let bound = binding_level(node);
        let mut written = self.visible_qualifiers(DeclaratorLevel { level: node, bound });
        written.push(self.text(stated).to_string());
        let mut level = wrapped(node);
        while let Some(held) = level {
            if let Some(mark) = self.shape(held) {
                written.push(mark);
                written.extend(self.visible_qualifiers(DeclaratorLevel { level: held, bound }));
            }
            level = wrapped(held);
        }
        written.join(" ")
    }

    /// Return the qualifiers one declarator level states that a caller of the signature can see.
    fn visible_qualifiers(&self, declarator: DeclaratorLevel<'_>) -> Vec<String> {
        if declarator.level == declarator.bound {
            return Vec::new();
        }
        children(declarator.level)
            .into_iter()
            .filter(|held| held.kind() == "type_qualifier")
            .map(|held| self.text(held).to_string())
            .collect()
    }

    /// Return what one declarator level adds to the type it wraps, as this language writes it.
    ///
    /// An array keeps its extent and a function keeps its parameter list, because `int (&)[4]` and
    /// `int (&)[8]` are two types and so are two callbacks that differ only in what they take.
    fn shape(&self, level: Syntax) -> Option<String> {
        match level.kind() {
            "pointer_declarator" => Some("*".to_string()),
            "reference_declarator" => Some(self.text(level.child(0)?).to_string()),
            "variadic_declarator" => Some("...".to_string()),
            "array_declarator" => Some(format!(
                "[{}]",
                level
                    .child_by_field_name("size")
                    .map(|size| self.text(size))
                    .unwrap_or_default()
            )),
            "function_declarator" => level
                .child_by_field_name("parameters")
                .map(|list| self.text(list).to_string()),
            _ => None,
        }
    }

    /// Return how widely one declaration reaches, by the way this language family states it.
    ///
    /// C narrows a name with `static` or an anonymous namespace, and C++ adds an access specifier
    /// that governs every member after it until the next one. Both are the same idea written in
    /// two places, and both land on the four levels every frontend fills.
    fn reach(&self, node: Syntax) -> Visibility {
        if let Some(holder) = enclosing_type(node) {
            return self.member_reach(MemberPosition {
                holder,
                member: node,
            });
        }
        if self.text(node).starts_with("static ") || in_anonymous_namespace(node) {
            return Visibility::Internal;
        }
        Visibility::Public
    }

    /// Return the access one member inherits from the specifier that most recently preceded it.
    fn member_reach(&self, position: MemberPosition<'_>) -> Visibility {
        let mut reach = self.default_member_reach(position.holder);
        let Some(body) = descendant(position.holder, "field_declaration_list") else {
            return reach;
        };
        for child in children(body) {
            if child.start_byte() > position.member.start_byte() {
                break;
            }
            if let Some(specified) = self.specified_reach(child) {
                reach = specified;
            }
        }
        reach
    }

    fn default_member_reach(&self, holder: Syntax<'_>) -> Visibility {
        match holder.child(0).map(|keyword| self.text(keyword)) {
            Some("class") => Visibility::Private,
            _ => Visibility::Public,
        }
    }

    fn specified_reach(&self, node: Syntax<'_>) -> Option<Visibility> {
        (node.kind() == "access_specifier").then(|| {
            match self.text(node).trim_end_matches(':').trim() {
                "private" => Visibility::Private,
                "protected" => Visibility::Protected,
                _ => Visibility::Public,
            }
        })
    }

    pub(in crate::native) fn class_fact(&self, root: Syntax) -> Value {
        let classes: Vec<Value> = walk(root)
            .into_iter()
            .filter(|node| is_type(*node))
            .filter_map(|node| {
                let name =
                    child(node, "type_identifier").map(|item| self.text(item).to_string())?;
                let members = descendant(node, "field_declaration_list");
                Some(json!({
                    "name": name,
                    "path": self.source.relative.clone(),
                    "span": self.locate(node),
                    "source": self.text(node),
                    "scope": "module",
                    "visibility": visibility(self.reach(node)),
                    "direct_bases": self.bases(node),
                    "methods": members
                        .map(|body| self.methods(TypeBody { holder: node, body }))
                        .unwrap_or_default(),
                    "field_count": members.map_or(0, |body| {
                        children(body)
                            .into_iter()
                            .filter(|member| {
                                member.kind() == "field_declaration"
                                    && descendant(*member, "function_declarator").is_none()
                            })
                            .count()
                    }),
                }))
            })
            .collect();
        JsonObject::new(self.base(&format!("classes:{}", self.source.relative), root))
            .merged(json!({"classes": classes}))
    }

    fn bases(&self, node: Syntax) -> Vec<String> {
        let Some(clause) = child(node, "base_class_clause") else {
            return Vec::new();
        };
        children(clause)
            .into_iter()
            .filter(|item| is_name(*item))
            .map(|item| self.text(item).to_string())
            .collect()
    }

    fn methods(&self, declared: TypeBody<'_>) -> Vec<Value> {
        children(declared.body)
            .into_iter()
            .filter(|member| {
                matches!(
                    member.kind(),
                    "field_declaration" | "function_definition" | "declaration"
                )
            })
            .filter_map(|member| {
                let declarator = descendant(member, "function_declarator")?;
                let name = self.declarator_name(declarator)?;
                let holder_name =
                    child(declared.holder, "type_identifier").map(|item| self.text(item));
                Some(json!({
                    "name": name.clone(),
                    "span": self.locate(member),
                    "source": self.text(member),
                    "kind": if Some(name.as_str()) == holder_name {
                        "constructor"
                    } else if name.starts_with('~') {
                        "destructor"
                    } else if self.text(member).starts_with("static ") {
                        "static_method"
                    } else {
                        "method"
                    },
                    "visibility": visibility(self.member_reach(MemberPosition {
                        holder: declared.holder,
                        member,
                    })),
                }))
            })
            .collect()
    }
}
