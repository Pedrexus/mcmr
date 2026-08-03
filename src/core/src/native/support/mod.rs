use crate::functions::ControlIncrement;
use tree_sitter::Node as Syntax;

mod control;
mod names;
mod syntax;

use control::Control;
pub(super) use names::{bare, dialect, is_qualifier, trim_include, visibility};
pub(super) use syntax::{
    binding_level, child, children, declarations, descendant, enclosing_type, executable_children,
    in_anonymous_namespace, is_name, is_type, native_parameter, statement_count, walk, wrapped,
};

pub(super) struct QualifiedNativeName<'scope>(&'scope str);

impl<'scope> QualifiedNativeName<'scope> {
    pub(super) fn new(scope: &'scope str) -> Self {
        Self(scope)
    }

    /// Return the repository-wide name one written name carries inside this scope.
    pub(super) fn with(self, named: &str) -> String {
        match self.0.is_empty() {
            true => named.to_string(),
            false => format!("{}::{named}", self.0),
        }
    }
}

/// What one node in a declaration's own tree is, in terms every language shares.
///
/// This is deliberately not a parse tree. A rule reading it asks what a body binds, what it calls,
/// and what it writes down, and this grammar buries all three under the shapes it needs to parse
/// C++. Anything the language adds beyond the shared kinds arrives as children rather than as a
/// kind nobody else has.
pub(super) fn kind_of(node: Syntax) -> &'static str {
    if is_type(node) {
        return "type";
    }
    match node.kind() {
        "function_definition" | "lambda_expression" => "callable",
        // A member whose declarator is a function states a method rather than a field, and the
        // rules that read the two read them for opposite reasons.
        "declaration" | "field_declaration" | "parameter_declaration" => {
            match descendant(node, "function_declarator") {
                Some(_) => "callable",
                None => "binding",
            }
        }
        "assignment_expression" | "init_declarator" => "binding",
        "return_statement" | "co_return_statement" => "return",
        "if_statement" | "switch_statement" | "case_statement" | "conditional_expression" => {
            "branch"
        }
        "for_statement" | "for_range_loop" | "while_statement" | "do_statement" => "loop",
        "try_statement" => "guard",
        "throw_statement" => "raise",
        "preproc_include" | "using_declaration" | "namespace_alias_definition" => "import",
        "expression_statement" => "effect",
        "call_expression" | "new_expression" => "call",
        "identifier"
        | "qualified_identifier"
        | "type_identifier"
        | "field_identifier"
        | "namespace_identifier"
        | "primitive_type"
        | "sized_type_specifier" => "name",
        "field_expression" => "member",
        "string_literal" | "raw_string_literal" | "concatenated_string" | "char_literal" => "text",
        "number_literal" | "true" | "false" | "null" | "nullptr" => "literal",
        "initializer_list" => "collection",
        "binary_expression" | "unary_expression" | "update_expression" | "pointer_expression" => {
            "operation"
        }
        "subscript_expression" => "index",
        "co_await_expression" => "await",
        "compound_statement" => "scope",
        _ => "statement",
    }
}

/// Whether one node carries no meaning of its own and hands its children to whatever holds it.
///
/// A grammar names every shape it needs to parse, and several of those exist only to group: the
/// block a body opens, the list an argument sits in, the parentheses around an expression, and the
/// clause a catch or an else introduces. A rule asks what a body does rather than which brackets
/// it used, so these contribute their children in place and cost the tree no depth.
pub(super) fn is_transparent(node: Syntax) -> bool {
    match node.kind() {
        // A statement that assigns is the binding it holds rather than a wrapper around one, so
        // it steps aside and lets the assignment be what the tree states.
        "expression_statement" => child(node, "assignment_expression").is_some(),
        "compound_statement"
        | "declaration_list"
        | "argument_list"
        | "parameter_list"
        | "subscript_argument_list"
        | "parenthesized_expression"
        | "condition_clause"
        | "init_declarator"
        | "else_clause"
        | "catch_clause"
        | "template_declaration"
        | "linkage_specification"
        | "attributed_statement"
        | "kernel_call_syntax" => true,
        _ => false,
    }
}

/// Whether one node is a declaration that carries a fact of its own.
pub(super) fn is_declaration(node: Syntax) -> bool {
    is_type(node) || node.kind() == "function_definition"
}

/// Return the child one node takes its own name from, which the tree never repeats beneath it.
pub(super) fn named_by(node: Syntax<'_>) -> Option<Syntax<'_>> {
    match node.kind() {
        "assignment_expression" => node.child_by_field_name("left"),
        "declaration" | "field_declaration" | "parameter_declaration" | "init_declarator" => {
            node.child_by_field_name("declarator")
        }
        _ => None,
    }
}

/// Return the node one statement is located at, which drops the punctuation that ends it.
///
/// A statement here ends in a semicolon where the expression it holds does not, and the rule
/// asking whether a statement produced only a value finds it by matching the child that covers
/// the whole statement. Locating an effect at its expression is what makes that match, and the
/// semicolon is punctuation rather than content.
pub(super) fn located(node: Syntax<'_>) -> Syntax<'_> {
    match node.kind() {
        "expression_statement" => children(node).into_iter().next().unwrap_or(node),
        _ => node,
    }
}

/// Whether one type declares a member every derived type has to write, which is `= 0`.
///
/// This is how C++ states a contract, and the grammar carries it exactly. A member declaration
/// whose declarator is a function and whose default value is written is a pure virtual, since a
/// function declaration is the only member the language lets anybody assign zero to. Reading the
/// declarator rather than the text is what keeps `int limit = 0;` out of the answer.
pub(super) fn declares_pure_virtual(node: Syntax) -> bool {
    let Some(body) = child(node, "field_declaration_list") else {
        return false;
    };
    children(body).into_iter().any(|member| {
        member.kind() == "field_declaration"
            && member
                .child_by_field_name("declarator")
                .is_some_and(|declarator| {
                    declarator.kind() == "function_declarator"
                        || descendant(declarator, "function_declarator").is_some()
                })
            && member.child_by_field_name("default_value").is_some()
    })
}

/// Return every control structure one native body holds and how deeply it is nested.
///
/// The shared complexity and nesting rules own the scoring model. This frontend only states the
/// same primitive evidence the Python, Rust, and TypeScript frontends state, so one program keeps
/// one meaning across languages and clang-tidy can serve as a differential oracle for the result.
pub(super) fn control_increments(body: Syntax<'_>) -> Vec<ControlIncrement> {
    let mut found = Control::default();
    found.read(body);
    found.increments
}

impl Control {
    fn record(&mut self, kind: &str) {
        self.increments
            .push(ControlIncrement::new(kind, self.depth));
    }

    fn inside(&mut self, node: Syntax<'_>) {
        self.depth += 1;
        self.read(node);
        self.depth -= 1;
    }

    /// Read one arm following `else` without charging an `else if` as a nested condition.
    fn alternative(&mut self, clause: Syntax<'_>) {
        self.record("alternative");
        let Some(body) = children(clause).into_iter().next() else {
            return;
        };
        match body.kind() {
            "if_statement" => {
                if let Some(consequence) = body.child_by_field_name("consequence") {
                    self.inside(consequence);
                }
                if let Some(otherwise) = body.child_by_field_name("alternative") {
                    self.alternative(otherwise);
                }
            }
            _ => self.inside(body),
        }
    }

    /// Read one syntax node for the structures it opens and the bodies they govern.
    fn read(&mut self, node: Syntax<'_>) {
        match node.kind() {
            "if_statement" => self.conditional(node),
            "for_statement" | "for_range_loop" | "while_statement" | "do_statement" => {
                self.control_body(node, "loop")
            }
            "switch_statement" => self.control_body(node, "switch"),
            "try_statement" => self.try_body(node),
            "function_definition" | "lambda_expression" => {}
            _ => children(node).into_iter().for_each(|held| self.read(held)),
        }
    }

    fn conditional(&mut self, node: Syntax<'_>) {
        self.record("conditional");
        if let Some(consequence) = node.child_by_field_name("consequence") {
            self.inside(consequence);
        }
        if let Some(otherwise) = node.child_by_field_name("alternative") {
            self.alternative(otherwise);
        }
    }

    fn control_body(&mut self, node: Syntax<'_>, kind: &str) {
        self.record(kind);
        if let Some(body) = node.child_by_field_name("body") {
            self.inside(body);
        }
    }

    fn try_body(&mut self, node: Syntax<'_>) {
        self.record("catch");
        children(node)
            .into_iter()
            .for_each(|held| self.inside(held));
    }
}
