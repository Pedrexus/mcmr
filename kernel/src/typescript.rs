use crate::discovery::Document;
use crate::graph::{
    Edge, EdgeKind, Language, Node, NodeKind, ParameterKind, Reference, Resolution, Stated,
    Visibility, attach, expand, identity, node, parameter, stray,
};
use crate::protocol::Stats;
use crate::source::Source;
use oxc_allocator::Allocator;
use oxc_ast::ast::{
    AccessorProperty, AssignmentExpression, AssignmentTarget, Class, ClassElement, Declaration,
    ExportAllDeclaration, ExportDefaultDeclaration, ExportDefaultDeclarationKind,
    ExportNamedDeclaration, Expression, FormalParameters, Function, FunctionBody,
    ImportDeclaration, ImportDeclarationSpecifier, MethodDefinition, Program, PropertyDefinition,
    PropertyKey, Statement, TSAccessibility, TSAnyKeyword, TSAsExpression, TSEnumDeclaration,
    TSInterfaceDeclaration, TSNonNullExpression, TSSignature, TSTypeAliasDeclaration,
    TSTypeAnnotation, TSTypeAssertion, TSTypeParameter, TSTypeParameterDeclaration,
    TSTypeReference, VariableDeclarator,
};
use oxc_ast::ast_kind::AstKind;
use oxc_ast_visit::Visit;
use oxc_ast_visit::walk::{
    walk_class, walk_function, walk_method_definition, walk_ts_as_expression,
    walk_ts_non_null_expression, walk_ts_type_assertion, walk_ts_type_parameter,
    walk_variable_declarator,
};
use oxc_parser::Parser;
use oxc_span::{GetSpan, SourceType, Span};
use oxc_syntax::scope::ScopeFlags;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// Build every requested fact family from one TypeScript document.
///
/// The families are the same ones the Python frontend fills, because a general rule reads the same
/// fact whichever language produced it. Only the spelling of a declaration differs: `export` is
/// the visibility keyword, a method sits in a class body, and an import names a path rather than a
/// package.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    let allocator = Allocator::default();
    let kind = SourceType::from_path(&document.relative).unwrap_or_default();
    let parsed = Parser::new(&allocator, &document.source, kind).parse();
    if parsed.panicked {
        stats.parse_failure_count += 1;
        return;
    }
    let source = Source::new(&document.relative, &document.source);
    let program = &parsed.program;
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_fact(&source, program));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(&source, program));
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(function_facts(&source, program));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(&source, program));
    }
    if let Some(stream) = facts.get_mut("ModuleSurfaceFact") {
        stream.push(surface(&source, program));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(syntax_facts(&source, program));
    }
}

/// Return one oxc span as the range every extractor in this kernel measures with.
fn range(span: Span) -> ruff_text_size::TextRange {
    ruff_text_size::TextRange::new(span.start.into(), span.end.into())
}

fn base(source: &Source, key: &str) -> Value {
    json!({
        "key": key,
        "span": source.span(range(Span::default())),
        "language": "typescript",
    })
}

fn merge(mut left: Value, right: Value) -> Value {
    if let (Some(target), Some(extra)) = (left.as_object_mut(), right.as_object()) {
        for (name, value) in extra {
            target.insert(name.clone(), value.clone());
        }
    }
    left
}

fn module_fact(source: &Source, program: &Program) -> Value {
    let classes = program
        .body
        .iter()
        .filter(|statement| declared_class(statement).is_some())
        .count();
    let functions = program
        .body
        .iter()
        .filter(|statement| declared_function(statement).is_some())
        .count();
    merge(
        base(source, &format!("module:{}", source.relative)),
        json!({
            "physical_line_count": source.text.lines().count(),
            "class_count": classes,
            "function_count": functions,
            "is_package_initializer": source.relative.ends_with("/index.ts"),
            "members": program
                .body
                .iter()
                .filter_map(declared_name)
                .map(|name| json!({"name": name, "responsibility": ""}))
                .collect::<Vec<_>>(),
        }),
    )
}

/// Return the class one statement declares, whether or not it is exported.
fn declared_class<'ast>(statement: &'ast Statement<'ast>) -> Option<&'ast Class<'ast>> {
    match statement {
        Statement::ClassDeclaration(item) => Some(item),
        Statement::ExportNamedDeclaration(item) => match item.declaration.as_ref()? {
            Declaration::ClassDeclaration(class) => Some(class),
            _ => None,
        },
        _ => None,
    }
}

/// Return the function one statement declares, whether or not it is exported.
fn declared_function<'ast>(statement: &'ast Statement<'ast>) -> Option<&'ast Function<'ast>> {
    match statement {
        Statement::FunctionDeclaration(item) => Some(item),
        Statement::ExportNamedDeclaration(item) => match item.declaration.as_ref()? {
            Declaration::FunctionDeclaration(function) => Some(function),
            _ => None,
        },
        _ => None,
    }
}

fn declared_name(statement: &Statement) -> Option<String> {
    if let Some(class) = declared_class(statement) {
        return class.id.as_ref().map(|name| name.name.to_string());
    }
    declared_function(statement)
        .and_then(|function| function.id.as_ref().map(|name| name.name.to_string()))
}

/// Whether one statement exports what it declares, which is what public means here.
fn is_exported(statement: &Statement) -> bool {
    matches!(
        statement,
        Statement::ExportNamedDeclaration(_) | Statement::ExportDefaultDeclaration(_)
    )
}

fn import_facts(source: &Source, program: &Program) -> Vec<Value> {
    let mut facts = Vec::new();
    for statement in &program.body {
        let Statement::ImportDeclaration(item) = statement else {
            continue;
        };
        let module = item.source.value.to_string();
        for specifier in item.specifiers.iter().flatten() {
            let bound = specifier.name().to_string();
            let references = source
                .text
                .matches(bound.as_str())
                .count()
                .saturating_sub(1);
            facts.push(merge(
                base(source, &format!("import:{}:{bound}", source.relative)),
                json!({
                    "name": bound,
                    "module": module.clone(),
                    "imported_name": bound,
                    "importer_module": source.relative.clone(),
                    "declaration": source.node("import", range(statement.span())),
                    "reference_count": references,
                    "has_qualifying_use": references > 0,
                    "is_relative": module.starts_with('.'),
                    "is_project_owned": module.starts_with('.'),
                    "is_external": !module.starts_with('.'),
                    "is_type_only": item.import_kind.is_type(),
                }),
            ));
        }
    }
    facts
}

fn function_facts(source: &Source, program: &Program) -> Vec<Value> {
    let mut facts = Vec::new();
    for statement in &program.body {
        if let Some(function) = declared_function(statement) {
            facts.push(function_fact(
                source,
                function,
                "module",
                is_exported(statement),
            ));
        }
        if let Some(class) = declared_class(statement) {
            for member in &class.body.body {
                if let ClassElement::MethodDefinition(method) = member
                    && let Some(name) = member_name(method)
                {
                    facts.push(method_fact(source, method, &name));
                }
            }
        }
    }
    facts
}

fn function_fact(source: &Source, function: &Function, scope: &str, exported: bool) -> Value {
    let name = function
        .id
        .as_ref()
        .map(|item| item.name.to_string())
        .unwrap_or_default();
    let increments = control_increments(function.body.as_deref());
    merge(
        base(source, &format!("function:{}:{name}", source.relative)),
        json!({
            "name": name,
            "scope": scope,
            "visibility": if exported { "public" } else { "internal" },
            "is_async": function.r#async,
            "implementation_lines": body_lines(source, function),
            "direct_statement_count": function
                .body
                .as_ref()
                .map(|body| body.statements.len())
                .unwrap_or(0),
            "conditional_count": conditionals(&increments),
            "control_increments": increments,
            "parameters": parameters(function),
            "definition": source.node("function", range(function.span())),
        }),
    )
}

/// Return how many physical lines one body runs, from its first statement to its last.
///
/// The signature and the braces are left out because they are not the work, which is the same
/// boundary the reference frontend draws when it drops the declaration line and the docstring.
fn body_lines(source: &Source, function: &Function) -> usize {
    let Some(body) = function.body.as_ref() else {
        return 0;
    };
    let (Some(first), Some(last)) = (body.statements.first(), body.statements.last()) else {
        return 0;
    };
    source.line_count(ruff_text_size::TextRange::new(
        range(first.span()).start(),
        range(last.span()).end(),
    ))
}

/// Return how many of the structures one body holds are plain conditions.
fn conditionals(increments: &[Value]) -> usize {
    increments
        .iter()
        .filter(|value| value["kind"] == "conditional")
        .count()
}

/// Return every control structure one body holds, each with the number enclosing it.
///
/// The kinds and the depth arithmetic are the reference frontend's, because the complexity and
/// nesting rules own one scoring model for every language and a second convention here would make
/// the same program measure differently depending on who wrote it. Only statements are read, which
/// is the same boundary the reference frontend draws, so a condition written as a ternary or inside
/// an arrow function is left to the callable that holds it.
fn control_increments(body: Option<&FunctionBody>) -> Vec<Value> {
    let mut found = Control::default();
    for statement in body.iter().flat_map(|held| held.statements.iter()) {
        found.read(statement);
    }
    found.increments
}

/// Every control structure one body states, collected as the walk meets them.
#[derive(Default)]
struct Control {
    depth: usize,
    increments: Vec<Value>,
}

impl Control {
    fn record(&mut self, kind: &str) {
        self.increments
            .push(json!({"kind": kind, "nesting_depth": self.depth}));
    }

    /// Walk one body knowing it sits one level deeper than the structure that opened it.
    fn inside(&mut self, held: &Statement) {
        self.depth += 1;
        self.read(held);
        self.depth -= 1;
    }

    /// Record one structure and read the body it selects.
    fn opens(&mut self, kind: &str, body: &Statement) {
        self.record(kind);
        self.inside(body);
    }

    /// Record one arm of a decision, which continues it rather than nesting inside it.
    ///
    /// `else if` is what this language spells `elif` with, so every arm of one chain sits at the
    /// depth the first `if` opened at. Reading the chain as a branch inside a branch would charge
    /// a reader a level of nesting the page never shows them.
    fn alternative(&mut self, otherwise: &Statement) {
        self.record("alternative");
        match otherwise {
            Statement::IfStatement(chained) => {
                self.inside(&chained.consequent);
                if let Some(next) = &chained.alternate {
                    self.alternative(next);
                }
            }
            held => self.inside(held),
        }
    }

    /// Read one statement for the structures it opens and the ones its body holds.
    ///
    /// A block, a label, and a `with` open no structure of their own and hand their contents on at
    /// the same depth, which is what keeps a brace a formatter added from reading as nesting. A
    /// nested declaration is not descended into at all, since it states a fact of its own.
    fn read(&mut self, statement: &Statement) {
        match statement {
            Statement::IfStatement(held) => {
                self.opens("conditional", &held.consequent);
                if let Some(otherwise) = &held.alternate {
                    self.alternative(otherwise);
                }
            }
            Statement::ForStatement(held) => self.opens("loop", &held.body),
            Statement::ForInStatement(held) => self.opens("loop", &held.body),
            Statement::ForOfStatement(held) => self.opens("loop", &held.body),
            Statement::WhileStatement(held) => self.opens("loop", &held.body),
            Statement::DoWhileStatement(held) => self.opens("loop", &held.body),
            Statement::SwitchStatement(held) => {
                self.record("switch");
                self.depth += 1;
                for case in &held.cases {
                    for inner in &case.consequent {
                        self.read(inner);
                    }
                }
                self.depth -= 1;
            }
            Statement::TryStatement(held) => {
                self.record("catch");
                self.depth += 1;
                for inner in &held.block.body {
                    self.read(inner);
                }
                for inner in held
                    .handler
                    .iter()
                    .flat_map(|clause| clause.body.body.iter())
                {
                    self.read(inner);
                }
                for inner in held.finalizer.iter().flat_map(|block| block.body.iter()) {
                    self.read(inner);
                }
                self.depth -= 1;
            }
            Statement::BlockStatement(held) => {
                for inner in &held.body {
                    self.read(inner);
                }
            }
            Statement::LabeledStatement(held) => self.read(&held.body),
            Statement::WithStatement(held) => self.read(&held.body),
            _ => {}
        }
    }
}

/// Return one class member as the fact a rule reads, at the visibility its class stated.
///
/// A private name arrives without the hash the source wrote, so the key rather than the name is
/// what says a member is private, and the `private` and `protected` keywords say the same thing
/// about a member spelled plainly.
fn method_fact(source: &Source, method: &MethodDefinition, name: &str) -> Value {
    let function = &method.value;
    let increments = control_increments(function.body.as_deref());
    merge(
        base(source, &format!("function:{}:{name}", source.relative)),
        json!({
            "name": name,
            "scope": "method",
            "visibility": member_visibility(method),
            "is_async": function.r#async,
            "implementation_lines": body_lines(source, function),
            "direct_statement_count": function
                .body
                .as_ref()
                .map(|body| body.statements.len())
                .unwrap_or(0),
            "conditional_count": conditionals(&increments),
            "control_increments": increments,
            "parameters": parameters(function),
            "definition": source.node("function", range(function.span())),
        }),
    )
}

fn parameters(function: &Function) -> Vec<Value> {
    function
        .params
        .items
        .iter()
        .map(|parameter| {
            json!({
                "name": parameter
                    .pattern
                    .get_identifier_name()
                    .map(|name| name.to_string())
                    .unwrap_or_default(),
                "is_required_by_external_contract": true,
            })
        })
        .collect()
}

/// Return the name one class member states, including the private form that carries a hash.
fn member_name(method: &oxc_ast::ast::MethodDefinition) -> Option<String> {
    match &method.key {
        oxc_ast::ast::PropertyKey::PrivateIdentifier(item) => Some(item.name.to_string()),
        key => key.static_name().map(|name| name.to_string()),
    }
}

/// Return how widely one class member reaches, by the two ways this language states it.
fn member_visibility(method: &oxc_ast::ast::MethodDefinition) -> &'static str {
    if matches!(method.key, oxc_ast::ast::PropertyKey::PrivateIdentifier(_)) {
        return "private";
    }
    match method.accessibility {
        Some(oxc_ast::ast::TSAccessibility::Private) => "private",
        Some(oxc_ast::ast::TSAccessibility::Protected) => "protected",
        _ => "public",
    }
}

fn class_fact(source: &Source, program: &Program) -> Value {
    let classes: Vec<Value> = program
        .body
        .iter()
        .filter_map(|statement| {
            let class = declared_class(statement)?;
            let name = class.id.as_ref()?.name.to_string();
            Some(json!({
                "name": name,
                "path": source.relative.clone(),
                "scope": "module",
                "visibility": if is_exported(statement) { "public" } else { "internal" },
                "direct_bases": class
                    .super_class
                    .as_ref()
                    .map(|base| vec![source.slice(range(base.span())).to_string()])
                    .unwrap_or_default(),
                "methods": class
                    .body
                    .body
                    .iter()
                    .filter_map(|member| match member {
                        ClassElement::MethodDefinition(method) => {
                            let name = member_name(method)?;
                            Some(json!({
                                "name": name.clone(),
                                "kind": if method.kind.is_constructor() {
                                    "constructor"
                                } else if method.kind.is_accessor() {
                                    "property"
                                } else if method.r#static {
                                    "static_method"
                                } else {
                                    "method"
                                },
                                "visibility": member_visibility(method),
                            }))
                        }
                        _ => None,
                    })
                    .collect::<Vec<_>>(),
                "field_count": class
                    .body
                    .body
                    .iter()
                    .filter(|member| matches!(member, ClassElement::PropertyDefinition(_)))
                    .count(),
            }))
        })
        .collect();
    merge(
        base(source, &format!("classes:{}", source.relative)),
        json!({"classes": classes}),
    )
}

/// What one module publishes, how far its callers reach for it, and where it steps around types.
pub fn surface(source: &Source, program: &Program) -> Value {
    let mut wholesale: Vec<String> = Vec::new();
    let mut named = 0;
    let mut exports = 0;
    let mut deepest = String::new();
    for statement in &program.body {
        match statement {
            Statement::ExportAllDeclaration(item) => {
                wholesale.push(item.source.value.to_string());
                deepest = climbed(deepest, &item.source.value);
            }
            Statement::ExportNamedDeclaration(item) => {
                exports += 1;
                if let Some(from) = &item.source {
                    named += item.specifiers.len();
                    deepest = climbed(deepest, &from.value);
                }
            }
            Statement::ExportDefaultDeclaration(_) => exports += 1,
            Statement::ImportDeclaration(item) => {
                deepest = climbed(deepest, &item.source.value);
            }
            _ => {}
        }
    }
    merge(
        base(source, &format!("surface:{}", source.relative)),
        json!({
            "star_reexport_count": wholesale.len(),
            "star_reexports": wholesale,
            "named_reexport_count": named,
            "export_count": exports,
            "is_index_module": source.relative.ends_with("/index.ts")
                || source.relative == "index.ts",
            "deepest_relative_import": relative_depth(&deepest),
            "deepest_relative_specifier": deepest,
            "erasable_violations": erasable(source, program),
            "escape_hatches": escape_hatches(source, program),
            "physical_line_count": source.text.lines().count(),
        }),
    )
}

/// Return whichever of two specifiers climbs further out of the directory that wrote it.
fn climbed(held: String, candidate: &str) -> String {
    match relative_depth(candidate) > relative_depth(&held) {
        true => candidate.to_string(),
        false => held,
    }
}

/// Return how many directories one relative import climbs before it finds its target.
fn relative_depth(specifier: &str) -> usize {
    specifier.matches("../").count()
}

/// Return each construct that type stripping cannot erase, which a runtime transform must handle.
///
/// A declaration reaches here whether it is exported or not, since `export enum Status` generates
/// exactly the object `enum Status` does and a reader stripping types is stopped by both.
fn erasable(source: &Source, program: &Program) -> Vec<Value> {
    program
        .body
        .iter()
        .filter_map(|statement| {
            let (kind, name, span) = surviving(statement)?;
            Some(json!({
                "kind": kind,
                "name": name,
                "line": source.line_of(range(span).start()),
            }))
        })
        .chain(parameter_properties(source, program))
        .collect()
}

/// Return what one statement declares that survives type stripping, looking through an export.
fn surviving(statement: &Statement) -> Option<(&'static str, String, Span)> {
    match statement {
        Statement::TSEnumDeclaration(item) => Some((
            if item.r#const { "const_enum" } else { "enum" },
            item.id.name.to_string(),
            item.span,
        )),
        Statement::TSModuleDeclaration(item) => {
            Some(("namespace", item.id.name().to_string(), item.span))
        }
        Statement::TSImportEqualsDeclaration(item) => {
            Some(("import_equals", item.id.name.to_string(), item.span))
        }
        Statement::ExportNamedDeclaration(item) => match item.declaration.as_ref()? {
            Declaration::TSEnumDeclaration(held) => Some((
                if held.r#const { "const_enum" } else { "enum" },
                held.id.name.to_string(),
                held.span,
            )),
            Declaration::TSModuleDeclaration(held) => {
                Some(("namespace", held.id.name().to_string(), held.span))
            }
            Declaration::TSImportEqualsDeclaration(held) => {
                Some(("import_equals", held.id.name.to_string(), held.span))
            }
            _ => None,
        },
        _ => None,
    }
}

/// Return each constructor parameter that also declares a field, which stripping cannot erase.
fn parameter_properties(source: &Source, program: &Program) -> Vec<Value> {
    program
        .body
        .iter()
        .filter_map(declared_class)
        .flat_map(|class| class.body.body.iter())
        .filter_map(|member| match member {
            ClassElement::MethodDefinition(method) if method.kind.is_constructor() => {
                Some(&method.value)
            }
            _ => None,
        })
        .flat_map(|function| function.params.items.iter())
        .filter(|parameter| parameter.accessibility.is_some() || parameter.readonly)
        .map(|parameter| {
            json!({
                "kind": "parameter_property",
                "name": parameter
                    .pattern
                    .get_identifier_name()
                    .map(|name| name.to_string())
                    .unwrap_or_default(),
                "line": source.line_of(range(parameter.span).start()),
            })
        })
        .collect()
}

/// Return each place the source steps around what its own type system proved.
///
/// This reads the tree rather than the text, which is the difference between a hatch and a word.
/// `as` is the keyword of a type assertion and also the keyword of every import and export rename,
/// so a barrel file re-exporting forty names under new ones is the shape a lexical reader calls
/// forty escape hatches and a parser calls none. The same holds one step down: `as const` widens
/// nothing and asserts nothing, a sentence in a comment is prose, and `"a as b"` is a string.
///
/// A suppression is the one hatch a tree cannot state, since it is written as a comment, and the
/// parser hands those over separately.
fn escape_hatches(source: &Source, program: &Program) -> Vec<Value> {
    let mut found = Hatches::default();
    found.visit_program(program);
    found.found.extend(
        program
            .comments
            .iter()
            .filter(|comment| suppresses(source.slice(range(comment.span))))
            .map(|comment| ("ignore_comment", comment.span)),
    );
    found.found.sort_by_key(|(_, span)| span.start);
    found
        .found
        .iter()
        .map(|(kind, span)| json!({"kind": kind, "line": source.line_of(range(*span).start())}))
        .collect()
}

/// Whether one comment turns the type checker off rather than saying something to a reader.
fn suppresses(text: &str) -> bool {
    text.contains("@ts-ignore") || text.contains("@ts-expect-error")
}

/// Every place one module steps around its own types, collected as the walk meets them.
#[derive(Default)]
struct Hatches {
    found: Vec<(&'static str, Span)>,
}

impl<'ast> Visit<'ast> for Hatches {
    /// `x as T` asserts, and `x as const` does not, since a literal widening to itself proves
    /// nothing away and is how this language spells an immutable literal at all.
    fn visit_ts_as_expression(&mut self, held: &TSAsExpression<'ast>) {
        if !held.type_annotation.is_const_type_reference() {
            self.found.push(("assertion", held.span));
        }
        walk_ts_as_expression(self, held);
    }

    fn visit_ts_type_assertion(&mut self, held: &TSTypeAssertion<'ast>) {
        self.found.push(("assertion", held.span));
        walk_ts_type_assertion(self, held);
    }

    fn visit_ts_non_null_expression(&mut self, held: &TSNonNullExpression<'ast>) {
        self.found.push(("non_null", held.span));
        walk_ts_non_null_expression(self, held);
    }

    fn visit_ts_any_keyword(&mut self, held: &TSAnyKeyword) {
        self.found.push(("any", held.span));
    }
}

/// How far down a declaration's tree a syntax fact reaches, matching every other frontend.
const SYNTAX_DEPTH: usize = 6;

/// Return every declaration this module states with the language-neutral tree its rules read.
fn syntax_facts(source: &Source, program: &Program) -> Vec<Value> {
    let mut facts = Vec::new();
    for statement in &program.body {
        syntax_statement(source, statement, &mut facts);
    }
    facts
}

/// Add the declarations one top-level statement carries, looking through an export wrapper.
fn syntax_statement(source: &Source, statement: &Statement, facts: &mut Vec<Value>) {
    match statement {
        Statement::FunctionDeclaration(function) => {
            syntax_function(source, function, "", facts);
        }
        Statement::ClassDeclaration(class) => syntax_class(source, class, facts),
        Statement::VariableDeclaration(declaration) => {
            syntax_variables(source, declaration, "", facts);
        }
        Statement::ExportNamedDeclaration(exported) => {
            let Some(declaration) = &exported.declaration else {
                return;
            };
            match declaration {
                Declaration::FunctionDeclaration(function) => {
                    syntax_function(source, function, "", facts);
                }
                Declaration::ClassDeclaration(class) => syntax_class(source, class, facts),
                Declaration::VariableDeclaration(variables) => {
                    syntax_variables(source, variables, "", facts);
                }
                _ => {}
            }
        }
        Statement::ExportDefaultDeclaration(exported) => match &exported.declaration {
            ExportDefaultDeclarationKind::FunctionDeclaration(function) => {
                syntax_function(source, function, "", facts);
            }
            ExportDefaultDeclarationKind::ClassDeclaration(class) => {
                syntax_class(source, class, facts);
            }
            _ => {}
        },
        _ => {}
    }
}

/// Add one named function, including its body when it has one.
fn syntax_function(source: &Source, function: &Function, owner: &str, facts: &mut Vec<Value>) {
    let Some(name) = function.id.as_ref().map(|item| item.name.to_string()) else {
        return;
    };
    let qualname = syntax_qualname(owner, &name);
    facts.push(syntax_declaration(
        source,
        &qualname,
        "callable",
        function.span,
        function.body.as_deref(),
    ));
}

/// Add one class and each method whose body is independently judged by a rule.
fn syntax_class(source: &Source, class: &Class, facts: &mut Vec<Value>) {
    let Some(name) = class.id.as_ref().map(|item| item.name.to_string()) else {
        return;
    };
    let methods: Vec<Value> = class
        .body
        .body
        .iter()
        .filter_map(|member| match member {
            ClassElement::MethodDefinition(method) => {
                let named = member_name(method)?;
                Some(syntax_node(
                    source,
                    "callable",
                    &named,
                    method.span,
                    Vec::new(),
                ))
            }
            _ => None,
        })
        .collect();
    let tree = syntax_node(source, "type", &name, class.span, methods);
    facts.push(crate::syntax::fact(
        source,
        "typescript",
        &name,
        tree,
        json!(source.span(range(class.span))),
    ));
    for member in &class.body.body {
        let ClassElement::MethodDefinition(method) = member else {
            continue;
        };
        let Some(named) = member_name(method) else {
            continue;
        };
        let qualname = syntax_qualname(&name, &named);
        facts.push(syntax_declaration(
            source,
            &qualname,
            "callable",
            method.span,
            method.value.body.as_deref(),
        ));
    }
}

/// Add each variable whose initializer is a callable as the declaration it creates.
fn syntax_variables(
    source: &Source,
    declaration: &oxc_ast::ast::VariableDeclaration<'_>,
    owner: &str,
    facts: &mut Vec<Value>,
) {
    for variable in &declaration.declarations {
        let Some(name) = variable.id.get_identifier_name() else {
            continue;
        };
        let (span, body) = match &variable.init {
            Some(Expression::ArrowFunctionExpression(function)) => {
                (variable.span, Some(function.body.as_ref()))
            }
            Some(Expression::FunctionExpression(function)) => {
                (variable.span, function.body.as_deref())
            }
            _ => continue,
        };
        facts.push(syntax_declaration(
            source,
            &syntax_qualname(owner, &name),
            "callable",
            span,
            body,
        ));
    }
}

fn syntax_qualname(owner: &str, name: &str) -> String {
    match owner.is_empty() {
        true => name.to_string(),
        false => format!("{owner}.{name}"),
    }
}

/// Assemble one declaration from its source and the semantic nodes its body states.
fn syntax_declaration(
    source: &Source,
    qualname: &str,
    kind: &str,
    span: Span,
    body: Option<&FunctionBody<'_>>,
) -> Value {
    let mut builder = SyntaxTree::new();
    if let Some(body) = body {
        builder.visit_function_body(body);
    }
    let tree = syntax_node(
        source,
        kind,
        qualname.rsplit('.').next().unwrap_or(qualname),
        span,
        builder
            .roots
            .into_iter()
            .map(|node| node.value(source, SYNTAX_DEPTH))
            .collect(),
    );
    crate::syntax::fact(
        source,
        "typescript",
        qualname,
        tree,
        json!(source.span(range(span))),
    )
}

fn syntax_node(
    source: &Source,
    kind: &str,
    name: &str,
    span: Span,
    children: Vec<Value>,
) -> Value {
    json!({
        "kind": crate::syntax::known(kind),
        "name": name,
        "text": source.slice(range(span)),
        "span": source.span(range(span)),
        "children": children,
    })
}

/// One semantic node waiting for the visitor to finish all children inside it.
struct SyntaxDraft {
    kind: &'static str,
    name: String,
    span: Span,
    children: Vec<SyntaxDraft>,
}

impl SyntaxDraft {
    fn value(self, source: &Source, depth: usize) -> Value {
        let children = match depth {
            0 => Vec::new(),
            _ => self
                .children
                .into_iter()
                .map(|child| child.value(source, depth - 1))
                .collect(),
        };
        syntax_node(source, self.kind, &self.name, self.span, children)
    }
}

/// Reduce an Oxc tree to the vocabulary every language-neutral syntax rule reads.
struct SyntaxTree {
    frames: Vec<Option<SyntaxDraft>>,
    roots: Vec<SyntaxDraft>,
}

impl SyntaxTree {
    fn new() -> Self {
        Self {
            frames: Vec::new(),
            roots: Vec::new(),
        }
    }

    fn draft(&self, kind: AstKind<'_>) -> Option<SyntaxDraft> {
        let span = kind.span();
        let (semantic, name, at) = match kind {
            AstKind::VariableDeclarator(item) => (
                "binding",
                item.id
                    .get_identifier_name()
                    .map(|name| name.to_string())
                    .unwrap_or_default(),
                span,
            ),
            AstKind::ExpressionStatement(item) => {
                ("effect", String::new(), item.expression.span())
            }
            AstKind::IfStatement(_) | AstKind::ConditionalExpression(_) => {
                ("branch", String::new(), span)
            }
            AstKind::ForStatement(_)
            | AstKind::ForInStatement(_)
            | AstKind::ForOfStatement(_)
            | AstKind::WhileStatement(_)
            | AstKind::DoWhileStatement(_) => ("loop", String::new(), span),
            AstKind::TryStatement(_) => ("guard", String::new(), span),
            AstKind::WithStatement(_) => ("scope", String::new(), span),
            AstKind::ReturnStatement(_) => ("return", String::new(), span),
            AstKind::ThrowStatement(_) => ("raise", String::new(), span),
            AstKind::DebuggerStatement(_) => ("effect", "debugger".to_string(), span),
            AstKind::CallExpression(item) => (
                "call",
                expression_name(&item.callee).unwrap_or_default(),
                span,
            ),
            AstKind::NewExpression(item) => (
                "call",
                expression_name(&item.callee).unwrap_or_default(),
                span,
            ),
            AstKind::StaticMemberExpression(item) => (
                "member",
                expression_name(&item.object)
                    .map(|owner| format!("{owner}.{}", item.property.name))
                    .unwrap_or_else(|| item.property.name.to_string()),
                span,
            ),
            AstKind::PrivateFieldExpression(item) => (
                "member",
                expression_name(&item.object)
                    .map(|owner| format!("{owner}.#{}", item.field.name))
                    .unwrap_or_else(|| format!("#{}", item.field.name)),
                span,
            ),
            AstKind::IdentifierReference(item) => ("name", item.name.to_string(), span),
            AstKind::ThisExpression(_) => ("name", "this".to_string(), span),
            AstKind::StringLiteral(_) | AstKind::TemplateLiteral(_) => {
                ("text", String::new(), span)
            }
            AstKind::BooleanLiteral(_)
            | AstKind::NullLiteral(_)
            | AstKind::NumericLiteral(_)
            | AstKind::BigIntLiteral(_) => ("literal", String::new(), span),
            AstKind::ArrayExpression(_) | AstKind::ObjectExpression(_) => {
                ("collection", String::new(), span)
            }
            AstKind::BinaryExpression(_)
            | AstKind::LogicalExpression(_)
            | AstKind::UnaryExpression(_)
            | AstKind::UpdateExpression(_) => ("operation", String::new(), span),
            AstKind::AssignmentExpression(_) => ("binding", String::new(), span),
            AstKind::AwaitExpression(_) => ("await", String::new(), span),
            _ => return None,
        };
        Some(SyntaxDraft {
            kind: semantic,
            name,
            span: at,
            children: Vec::new(),
        })
    }
}

impl<'ast> Visit<'ast> for SyntaxTree {
    fn enter_node(&mut self, kind: AstKind<'ast>) {
        self.frames.push(self.draft(kind));
    }

    fn leave_node(&mut self, _kind: AstKind<'ast>) {
        let Some(Some(node)) = self.frames.pop() else {
            return;
        };
        if let Some(parent) = self.frames.iter_mut().rev().find_map(Option::as_mut) {
            parent.children.push(node);
        } else {
            self.roots.push(node);
        }
    }

    /// A nested callable carries its own fact, so its body never counts against its owner too.
    fn visit_function(&mut self, _function: &Function<'ast>, _flags: ScopeFlags) {}

    /// An arrow function is a declaration when a binding owns it and otherwise a nested callable.
    fn visit_arrow_function_expression(
        &mut self,
        _function: &oxc_ast::ast::ArrowFunctionExpression<'ast>,
    ) {
    }

    /// A nested class carries declarations of its own and contributes no body to its owner.
    fn visit_class(&mut self, _class: &Class<'ast>) {}
}

/// Build the part of the repository graph one TypeScript file states.
pub fn graph(source: Source, module: &str, specifiers: &Specifiers) -> Option<Stated> {
    let allocator = Allocator::default();
    let kind = SourceType::from_path(&source.relative).unwrap_or_default();
    // The parse borrows the text for as long as the tree lives, and the collector reads positions
    // back out of the same document, so the two hold one copy each rather than one borrowing the
    // other for the whole walk.
    let text = source.text.clone();
    let parsed = Parser::new(&allocator, &text, kind).parse();
    if parsed.panicked {
        return None;
    }
    let mut collector = Collector::new(source, module.to_string(), specifiers);
    collector.visit_program(&parsed.program);
    Some(collector.stated())
}

/// Where one written import specifier lands.
#[derive(Debug, PartialEq, Eq)]
pub enum Located {
    /// A module this repository declares, under the name the whole graph knows it by.
    Module(String),
    /// A package outside this repository, named the way a manifest would install it.
    Package(String),
    /// A path inside this repository that names no module this kernel read.
    Unsettled(String),
}

/// How this repository settles an import specifier, which TypeScript decides by path.
///
/// Three rules answer, and all three are read rather than guessed. A relative specifier walks from
/// the file that wrote it and usually leaves the extension off, so `./thing` reaches `thing.ts`,
/// `thing.d.ts`, or `thing/index.ts` and only the set of files says which. A specifier a
/// `tsconfig.json` maps takes the target that mapping states, following the `extends` chain,
/// because a framework states its own aliases in a generated config the checkout inherits.
/// Anything else names a package the project installs rather than a module it owns.
pub struct Specifiers {
    modules: BTreeSet<String>,
    tables: Vec<Table>,
}

/// The alias mappings one configuration file states, and the directory those mappings govern.
struct Table {
    directory: String,
    mappings: Vec<Mapping>,
}

/// One `paths` entry, as the specifier prefix it matches and the module prefixes it stands for.
struct Mapping {
    pattern: String,
    targets: Vec<String>,
}

impl Mapping {
    /// Return what one specifier becomes under this mapping, when this mapping matches it.
    fn apply(&self, specifier: &str) -> Option<Vec<String>> {
        let Some((head, tail)) = self.pattern.split_once('*') else {
            return (self.pattern == specifier).then(|| self.targets.clone());
        };
        let held = specifier.strip_prefix(head)?.strip_suffix(tail)?;
        Some(
            self.targets
                .iter()
                .map(|target| target.replacen('*', held, 1))
                .collect(),
        )
    }
}

impl Specifiers {
    /// Read every configuration that governs a TypeScript file of this repository.
    pub fn of(root: &str, modules: BTreeSet<String>) -> Self {
        let mut tables = Vec::new();
        let mut visited: BTreeSet<String> = BTreeSet::new();
        for module in &modules {
            let mut directory = parent_of(module).to_string();
            loop {
                if visited.insert(directory.clone())
                    && let Some(mappings) = mappings_at(Path::new(root), &directory)
                {
                    tables.push(Table {
                        directory: directory.clone(),
                        mappings,
                    });
                }
                if directory.is_empty() {
                    break;
                }
                directory = parent_of(&directory).to_string();
            }
        }
        // The configuration nearest a file is the one that governs it, so the deepest directory
        // is asked first and a repository-wide config only answers what no nearer one did.
        tables.sort_by_key(|table| std::cmp::Reverse(table.directory.len()));
        Self { modules, tables }
    }

    /// Return where one specifier written in one file lands.
    pub fn locate(&self, from: &str, specifier: &str) -> Located {
        if specifier.starts_with('.') {
            let written = normalized(&joined_path(parent_of(from), specifier));
            return match self.settle(&written) {
                Some(module) => Located::Module(module),
                None => Located::Unsettled(written),
            };
        }
        for table in &self.tables {
            if !governs(&table.directory, from) {
                continue;
            }
            for mapping in &table.mappings {
                let Some(candidates) = mapping.apply(specifier) else {
                    continue;
                };
                if let Some(module) = candidates.iter().find_map(|base| self.settle(base)) {
                    return Located::Module(module);
                }
                return Located::Unsettled(candidates.into_iter().next().unwrap_or_default());
            }
        }
        Located::Package(package_of(specifier))
    }

    /// Return the module one written path names, trying every file TypeScript would try.
    fn settle(&self, written: &str) -> Option<String> {
        let stem = without_suffix(written);
        [
            stem.to_string(),
            format!("{stem}.d"),
            format!("{stem}/index"),
            format!("{stem}/index.d"),
        ]
        .into_iter()
        .find(|candidate| self.modules.contains(candidate))
    }
}

/// Whether a configuration in one directory governs the file at one path.
fn governs(directory: &str, path: &str) -> bool {
    directory.is_empty() || path.starts_with(&format!("{directory}/"))
}

/// Return the mappings the configuration in one directory states, across its `extends` chain.
///
/// A `paths` entry is written against the file that declares it, so each step of the chain
/// rewrites its own targets against its own directory before they join the table. The walk is
/// bounded because a configuration that extended itself would otherwise loop.
fn mappings_at(root: &Path, directory: &str) -> Option<Vec<Mapping>> {
    let named = ["tsconfig.json", "jsconfig.json"]
        .into_iter()
        .find(|name| root.join(directory).join(name).exists())?;
    let mut mappings = Vec::new();
    let mut at = joined_path(directory, named);
    for _ in 0..8 {
        let Some(config) = read_config(&root.join(&at)) else {
            break;
        };
        let holder = parent_of(&at).to_string();
        let options = &config["compilerOptions"];
        let base = normalized(&joined_path(
            &holder,
            options["baseUrl"].as_str().unwrap_or("."),
        ));
        for (pattern, targets) in options["paths"].as_object().into_iter().flatten() {
            mappings.push(Mapping {
                pattern: pattern.clone(),
                targets: targets
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(|target| normalized(&joined_path(&base, target)))
                    .collect(),
            });
        }
        // A configuration published as a package lives under `node_modules`, which no scan of
        // this repository reads, so only a chain written as a path is followed.
        let Some(extends) = config["extends"]
            .as_str()
            .filter(|held| held.starts_with('.'))
        else {
            break;
        };
        at = normalized(&joined_path(&holder, extends));
        if !at.ends_with(".json") {
            at.push_str("/tsconfig.json");
        }
    }
    Some(mappings)
}

/// Read one configuration file, allowing the comments and trailing commas JSON forbids.
///
/// Every editor writes a `tsconfig.json` with comments in it, so a strict reader would decline the
/// one file that states the aliases this resolution needs.
fn read_config(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&plain_json(&text)).ok()
}

/// Return one commented document as the plain JSON a strict reader accepts.
fn plain_json(text: &str) -> String {
    let mut plain = String::with_capacity(text.len());
    let mut letters = text.chars().peekable();
    let mut inside_text = false;
    let mut escaping = false;
    while let Some(letter) = letters.next() {
        if inside_text {
            plain.push(letter);
            if escaping {
                escaping = false;
            } else if letter == '\\' {
                escaping = true;
            } else if letter == '"' {
                inside_text = false;
            }
            continue;
        }
        match (letter, letters.peek()) {
            ('/', Some('/')) => while letters.next_if(|held| *held != '\n').is_some() {},
            ('/', Some('*')) => {
                letters.next();
                let mut closing = false;
                for held in letters.by_ref() {
                    if closing && held == '/' {
                        break;
                    }
                    closing = held == '*';
                }
            }
            _ => {
                inside_text = letter == '"';
                plain.push(letter);
            }
        }
    }
    without_trailing_commas(&plain)
}

/// Return one comment-free document with the trailing commas a strict reader rejects removed.
fn without_trailing_commas(text: &str) -> String {
    let mut plain = String::with_capacity(text.len());
    let mut inside_text = false;
    let mut escaping = false;
    let mut pending = false;
    for letter in text.chars() {
        if inside_text {
            plain.push(letter);
            if escaping {
                escaping = false;
            } else if letter == '\\' {
                escaping = true;
            } else if letter == '"' {
                inside_text = false;
            }
            continue;
        }
        if letter.is_whitespace() {
            continue;
        }
        if letter == ',' {
            pending = true;
            continue;
        }
        if pending && !matches!(letter, '}' | ']') {
            plain.push(',');
        }
        pending = false;
        inside_text = letter == '"';
        plain.push(letter);
    }
    plain
}

/// Return one path with the module suffix a specifier may write stripped off it.
///
/// A specifier states `./thing`, `./thing.ts`, or `./thing.js`, and all three name the same module
/// because TypeScript resolves an emitted extension back to the source that produced it. Anything
/// else, such as a `.svelte` or a `.json`, keeps its suffix and settles against nothing.
fn without_suffix(path: &str) -> &str {
    const SUFFIXES: &[&str] = &[".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"];
    SUFFIXES
        .iter()
        .find_map(|suffix| path.strip_suffix(suffix))
        .unwrap_or(path)
}

/// Return the package one bare specifier names, which is what a manifest would install.
fn package_of(specifier: &str) -> String {
    let parts: Vec<&str> = specifier.split('/').collect();
    let taken = if specifier.starts_with('@') { 2 } else { 1 };
    parts[..taken.min(parts.len())].join("/")
}

fn parent_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

fn joined_path(holder: &str, name: &str) -> String {
    if holder.is_empty() {
        return name.to_string();
    }
    format!("{holder}/{name}")
}

/// Return one path with the `.` and `..` steps a specifier writes walked out of it.
fn normalized(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for step in path.split('/') {
        match step {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            name => parts.push(name),
        }
    }
    parts.join("/")
}

/// Write one import as the module it names beside the symbol it takes from it.
///
/// Both halves have to survive into resolution, which reads a reference as one string. A module is
/// a path and may hold a dot of its own, while an imported name never can, so the last dot is the
/// join and an empty tail means the whole module was reached rather than one name in it.
fn imported(module: &str, name: &str) -> String {
    format!("{module}.{name}")
}

fn split_import(expression: &str) -> (&str, &str) {
    expression.rsplit_once('.').unwrap_or((expression, ""))
}

/// What one declaration is called and what holds it, which every name inside it is written under.
#[derive(Clone)]
struct Owner {
    id: String,
    kind: NodeKind,
    qualname: String,
}

/// Collect every definition and reference one TypeScript file states.
///
/// The walk is the parser's own visitor with the declaring nodes overridden, so a construct this
/// frontend says nothing about is still descended into and the calls inside it are still recorded.
struct Collector<'ts> {
    source: Source,
    module: String,
    specifiers: &'ts Specifiers,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    references: Vec<Reference>,
    aliases: BTreeMap<String, String>,
    /// What each name bound from outside this repository stands for, which needs no resolution.
    externals: BTreeMap<String, String>,
    /// Every name an export statement names apart from the declaration itself.
    exported: BTreeSet<String>,
    /// Every type parameter this file binds, which stands for a type rather than naming one.
    generics: BTreeSet<String>,
    placed: BTreeSet<String>,
    owners: Vec<Owner>,
    classes: Vec<String>,
    exporting: bool,
}

impl<'ts> Collector<'ts> {
    fn new(source: Source, module: String, specifiers: &'ts Specifiers) -> Self {
        let owner = Owner {
            id: identity(Language::TypeScript, NodeKind::Module, &module),
            kind: NodeKind::Module,
            qualname: module.clone(),
        };
        Self {
            source,
            module,
            specifiers,
            nodes: Vec::new(),
            edges: Vec::new(),
            references: Vec::new(),
            aliases: BTreeMap::new(),
            externals: BTreeMap::new(),
            exported: BTreeSet::new(),
            generics: BTreeSet::new(),
            placed: BTreeSet::new(),
            owners: vec![owner],
            classes: Vec::new(),
            exporting: false,
        }
    }

    /// Return everything this file states, with the names a later export statement raised.
    ///
    /// `export { helper }` is written after the declaration it publishes, so what the declaration
    /// reaches is only settled once the whole file has been read.
    fn stated(mut self) -> Stated {
        let prefix = format!("{}.", self.module);
        for declared in &mut self.nodes {
            if let Some(name) = declared.qualname.strip_prefix(&prefix)
                && !name.contains('.')
                && self.exported.contains(name)
            {
                declared.visibility = Visibility::Public;
            }
        }
        Stated {
            nodes: self.nodes,
            edges: self.edges,
            references: self.references,
            aliases: self.aliases,
        }
    }

    fn owner(&self) -> Owner {
        self.owners.last().cloned().unwrap_or_else(|| Owner {
            id: identity(Language::TypeScript, NodeKind::Module, &self.module),
            kind: NodeKind::Module,
            qualname: self.module.clone(),
        })
    }

    fn line(&self, span: Span) -> usize {
        self.source.line_of(range(span).start())
    }

    /// Return one span as the single-line text an annotation is written down as.
    fn rendered(&self, span: Span) -> String {
        self.source
            .slice(range(span))
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Return how widely a declaration at this point reaches.
    ///
    /// `export` is what public means at module scope, a class member is as reachable as the class
    /// unless it says otherwise, and anything declared inside a callable is reachable from nowhere
    /// else whatever the file exports.
    fn reach(&self) -> Visibility {
        match self.owner().kind {
            NodeKind::Module if self.exporting => Visibility::Public,
            NodeKind::Module => Visibility::Internal,
            NodeKind::Class => Visibility::Public,
            _ => Visibility::Internal,
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
        declared.visibility = reach;
        declared
    }

    fn declare(&mut self, declared: Node, span: Span) -> Owner {
        let owner = Owner {
            id: declared.id.clone(),
            kind: declared.kind,
            qualname: declared.qualname.clone(),
        };
        let holder = self.owner().id;
        if self.placed.insert(owner.id.clone()) {
            self.nodes.push(declared);
        }
        self.relate(&holder, &owner.id, EdgeKind::Define, span);
        owner
    }

    fn enter(&mut self, owner: Owner) {
        self.owners.push(owner);
    }

    fn leave(&mut self) {
        self.owners.pop();
    }

    fn relate(&mut self, source: &str, target: &str, kind: EdgeKind, span: Span) {
        self.edges.push(Edge {
            source: source.to_string(),
            target: target.to_string(),
            kind,
            path: self.source.relative.clone(),
            line: self.line(span),
            resolution: Resolution::Exact,
        });
    }

    /// Record one name this file reaches for, which resolution then joins to a declaration.
    ///
    /// A name bound from a package is the exception, because the import already said where it
    /// comes from. Attaching it here keeps a dependency out of the unresolved set, which is where
    /// a gap in this kernel belongs and nothing else does.
    fn reference(&mut self, source: &str, expression: &str, kind: EdgeKind, span: Span) {
        if expression.is_empty() {
            return;
        }
        let head = expression.split('.').next().unwrap_or_default();
        if self.externals.contains_key(head) {
            let named = expand(expression, &self.externals);
            self.outside(source, NodeKind::ExternalSymbol, &named, kind, span);
            return;
        }
        self.references.push(Reference {
            language: Language::TypeScript,
            source: source.to_string(),
            expression: expression.to_string(),
            module: self.module.clone(),
            owner: self.classes.last().cloned(),
            receiver_type: None,
            kind,
            path: self.source.relative.clone(),
            line: self.line(span),
        });
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
        if self.placed.insert(target.clone()) {
            self.nodes.push(declared);
        }
        self.edges.push(Edge {
            source: source.to_string(),
            target,
            kind: relation,
            path: self.source.relative.clone(),
            line: self.line(span),
            resolution: Resolution::External,
        });
    }

    /// Record what one import or re-export reaches, and what each binding it makes now names.
    ///
    /// A binding with no imported name is the whole module, which is what a namespace import, a
    /// side effect import, and a wholesale re-export each take.
    fn reached(&mut self, located: &Located, bindings: &[(String, String)], span: Span) {
        let owner = identity(Language::TypeScript, NodeKind::Module, &self.module);
        if let Located::Package(package) = located {
            self.outside(
                &owner,
                NodeKind::ExternalModule,
                package,
                EdgeKind::Import,
                span,
            );
            for (bound, name) in bindings {
                let held = match name.is_empty() {
                    true => package.clone(),
                    false => imported(package, name),
                };
                if !name.is_empty() {
                    self.outside(
                        &owner,
                        NodeKind::ExternalSymbol,
                        &held,
                        EdgeKind::Access,
                        span,
                    );
                }
                self.externals.insert(bound.clone(), held);
            }
            return;
        }
        let (Located::Module(target) | Located::Unsettled(target)) = located else {
            return;
        };
        let settles = matches!(located, Located::Module(_));
        if bindings.is_empty() {
            self.import(&owner, target, "", span);
        }
        for (bound, name) in bindings {
            let held = match name.is_empty() {
                true => target.clone(),
                false => imported(target, name),
            };
            self.aliases.insert(bound.clone(), held.clone());
            self.import(&owner, target, name, span);
            // A path that settles on no module says everything it can say once. Naming each
            // symbol of it as well would report one gap per binding where there is one gap.
            if settles && !name.is_empty() {
                self.reference(&owner, &held, EdgeKind::Access, span);
            }
        }
    }

    fn import(&mut self, owner: &str, target: &str, name: &str, span: Span) {
        self.references.push(Reference {
            language: Language::TypeScript,
            source: owner.to_string(),
            expression: imported(target, name),
            module: self.module.clone(),
            owner: None,
            receiver_type: None,
            kind: EdgeKind::Import,
            path: self.source.relative.clone(),
            line: self.line(span),
        });
    }

    /// Declare one class, interface, alias, or enum, and state whether it is a contract.
    fn datatype(&mut self, named: &str, span: Span, is_contract: bool) -> Owner {
        let mut declared = self.place(NodeKind::Class, named, span, self.reach());
        declared.is_abstract = is_contract;
        self.declare(declared, span)
    }

    /// Walk what one callable states after its own declaration: its signature and its body.
    fn signature(
        &mut self,
        owner: Owner,
        generics: Option<&TSTypeParameterDeclaration<'_>>,
        params: &FormalParameters<'_>,
        returns: Option<&TSTypeAnnotation<'_>>,
        body: Option<&FunctionBody<'_>>,
    ) {
        self.enter(owner);
        if let Some(generics) = generics {
            self.visit_ts_type_parameter_declaration(generics);
        }
        self.parameters(params);
        if let Some(returns) = returns {
            self.visit_ts_type_annotation(returns);
        }
        if let Some(body) = body {
            self.visit_function_body(body);
        }
        self.leave();
    }

    /// Declare every position one signature states, in the order a caller fills them.
    ///
    /// TypeScript offers no way to name an argument at a call site, so every position binds
    /// positionally and a rest parameter swallows the tail. What a caller may leave out is stated
    /// two ways, as a default and as the `?` that makes a position optional, and both mean the
    /// same thing to anybody comparing two signatures.
    ///
    /// A destructured position binds no name a caller could ever pass, so it declares no node
    /// while still holding its place in the ordinals, which is what the Rust frontend also does.
    fn parameters(&mut self, params: &FormalParameters<'_>) {
        let owner = self.owner();
        let ordinary = params.items.iter().map(|held| {
            (
                held.pattern.get_identifier_name(),
                ParameterKind::PositionalOnly,
                held.initializer.is_some() || held.optional,
                held.type_annotation.as_deref(),
                held.span,
            )
        });
        let rest = params.rest.iter().map(|held| {
            (
                held.rest.argument.get_identifier_name(),
                ParameterKind::VarPositional,
                false,
                held.type_annotation.as_deref(),
                held.span,
            )
        });
        for (ordinal, (named, kind, optional, annotation, span)) in
            ordinary.chain(rest).enumerate()
        {
            if let Some(annotation) = annotation {
                self.visit_ts_type_annotation(annotation);
            }
            let Some(named) = named else {
                continue;
            };
            let mut declared = parameter(
                Language::TypeScript,
                &format!("{}.{named}", owner.qualname),
                ordinal,
                kind,
                optional,
            );
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(self.line(span));
            declared.annotation =
                annotation.map(|held| self.rendered(held.type_annotation.span()));
            let id = declared.id.clone();
            if self.placed.insert(id.clone()) {
                self.nodes.push(declared);
            }
            self.relate(&owner.id, &id, EdgeKind::Define, span);
        }
    }

    /// Declare the fields a constructor states in its own parameter list.
    ///
    /// A parameter carrying an access modifier or `readonly` declares a field of the class as well
    /// as a position of the constructor, and nothing else in the class body says so.
    fn fields(&mut self, method: &MethodDefinition<'_>) {
        for held in &method.value.params.items {
            if held.accessibility.is_none() && !held.readonly {
                continue;
            }
            let Some(named) = held.pattern.get_identifier_name() else {
                continue;
            };
            let mut declared = self.place(
                NodeKind::Attribute,
                &named,
                held.span,
                stated_reach(held.accessibility),
            );
            declared.annotation = held
                .type_annotation
                .as_ref()
                .map(|annotation| self.rendered(annotation.type_annotation.span()));
            self.declare(declared, held.span);
        }
    }

    /// Declare one member of an interface, which states a name without implementing it.
    fn signatures(
        &mut self,
        owner: Owner,
        generics: Option<&TSTypeParameterDeclaration<'_>>,
        body: &[TSSignature<'_>],
    ) {
        self.enter(owner);
        if let Some(generics) = generics {
            self.visit_ts_type_parameter_declaration(generics);
        }
        for member in body {
            match member {
                TSSignature::TSPropertySignature(held) => {
                    let Some(named) = key_name(&held.key) else {
                        continue;
                    };
                    let mut declared =
                        self.place(NodeKind::Attribute, &named, held.span, Visibility::Public);
                    declared.annotation = held
                        .type_annotation
                        .as_ref()
                        .map(|annotation| self.rendered(annotation.type_annotation.span()));
                    self.declare(declared, held.span);
                    if let Some(annotation) = &held.type_annotation {
                        self.visit_ts_type_annotation(annotation);
                    }
                }
                TSSignature::TSMethodSignature(held) => {
                    let Some(named) = key_name(&held.key) else {
                        continue;
                    };
                    let mut declared =
                        self.place(NodeKind::Method, &named, held.span, Visibility::Public);
                    declared.return_annotation = held
                        .return_type
                        .as_ref()
                        .map(|annotation| self.rendered(annotation.type_annotation.span()));
                    let member = self.declare(declared, held.span);
                    self.signature(
                        member,
                        held.type_parameters.as_deref(),
                        &held.params,
                        held.return_type.as_deref(),
                        None,
                    );
                }
                _ => {}
            }
        }
        self.leave();
    }

    /// Declare one binding whose value is a callable, which is how most of this language writes one.
    fn bound_callable(&mut self, named: &str, item: &VariableDeclarator<'_>) -> bool {
        match &item.init {
            Some(Expression::ArrowFunctionExpression(held)) => {
                let mut declared = self.place(NodeKind::Function, named, item.span, self.reach());
                declared.asynchronous = held.r#async;
                declared.return_annotation = held
                    .return_type
                    .as_ref()
                    .map(|annotation| self.rendered(annotation.type_annotation.span()));
                let owner = self.declare(declared, item.span);
                self.signature(
                    owner,
                    held.type_parameters.as_deref(),
                    &held.params,
                    held.return_type.as_deref(),
                    Some(&held.body),
                );
                true
            }
            Some(Expression::FunctionExpression(held)) => {
                let mut declared = self.place(NodeKind::Function, named, item.span, self.reach());
                declared.asynchronous = held.r#async;
                let owner = self.declare(declared, item.span);
                self.signature(
                    owner,
                    held.type_parameters.as_deref(),
                    &held.params,
                    held.return_type.as_deref(),
                    held.body.as_deref(),
                );
                true
            }
            Some(Expression::ClassExpression(held)) => {
                self.class(named, held);
                true
            }
            _ => false,
        }
    }

    /// Declare one class, what it derives from, and what it promises to satisfy.
    fn class(&mut self, named: &str, item: &Class<'_>) {
        let owner = self.datatype(named, item.span, item.r#abstract);
        if let Some(base) = &item.super_class
            && let Some(name) = expression_name(base)
        {
            self.reference(&owner.id, &name, EdgeKind::Inherit, base.span());
        }
        for implemented in &item.implements {
            let name = implemented.expression.to_string();
            self.reference(&owner.id, &name, EdgeKind::Inherit, implemented.span);
        }
        self.classes.push(owner.qualname.clone());
        self.enter(owner);
        if let Some(generics) = &item.type_parameters {
            self.visit_ts_type_parameter_declaration(generics);
        }
        self.visit_class_body(&item.body);
        self.leave();
        self.classes.pop();
    }
}

/// Walk what one file declares and what its bodies reach.
impl<'ast> Visit<'ast> for Collector<'_> {
    fn visit_import_declaration(&mut self, item: &ImportDeclaration<'ast>) {
        let located = self
            .specifiers
            .locate(&self.source.relative, &item.source.value);
        let bindings: Vec<(String, String)> = item
            .specifiers
            .iter()
            .flatten()
            .map(|specifier| match specifier {
                ImportDeclarationSpecifier::ImportSpecifier(held) => (
                    held.local.name.to_string(),
                    held.imported.name().to_string(),
                ),
                ImportDeclarationSpecifier::ImportDefaultSpecifier(held) => {
                    (held.local.name.to_string(), "default".to_string())
                }
                ImportDeclarationSpecifier::ImportNamespaceSpecifier(held) => {
                    (held.local.name.to_string(), String::new())
                }
            })
            .collect();
        self.reached(&located, &bindings, item.span);
    }

    fn visit_export_named_declaration(&mut self, item: &ExportNamedDeclaration<'ast>) {
        if let Some(from) = &item.source {
            let located = self.specifiers.locate(&self.source.relative, &from.value);
            let bindings: Vec<(String, String)> = item
                .specifiers
                .iter()
                .map(|specifier| {
                    (
                        specifier.exported.name().to_string(),
                        specifier.local.name().to_string(),
                    )
                })
                .collect();
            self.reached(&located, &bindings, item.span);
            return;
        }
        for specifier in &item.specifiers {
            let published = specifier.exported.name().to_string();
            let local = specifier.local.name().to_string();
            self.exported.insert(local.clone());
            self.exported.insert(published.clone());
            // Publishing a name under the name it already has says nothing a binding does not
            // already say, and recording it would overwrite the import this module hands on.
            if published == local {
                continue;
            }
            let target = self
                .aliases
                .get(&local)
                .cloned()
                .unwrap_or_else(|| imported(&self.module, &local));
            self.aliases.insert(published, target);
        }
        if let Some(declaration) = &item.declaration {
            self.exporting = true;
            self.visit_declaration(declaration);
            self.exporting = false;
        }
    }

    fn visit_export_default_declaration(&mut self, item: &ExportDefaultDeclaration<'ast>) {
        let named = match &item.declaration {
            ExportDefaultDeclarationKind::FunctionDeclaration(held) => {
                held.id.as_ref().map(|id| id.name.to_string())
            }
            ExportDefaultDeclarationKind::ClassDeclaration(held) => {
                held.id.as_ref().map(|id| id.name.to_string())
            }
            ExportDefaultDeclarationKind::TSInterfaceDeclaration(held) => {
                Some(held.id.name.to_string())
            }
            ExportDefaultDeclarationKind::Identifier(held) => Some(held.name.to_string()),
            _ => None,
        };
        // A default export is imported under whatever name the importer chooses, so the module
        // records what `default` stands for and the importer's binding walks that one step.
        if let Some(named) = named {
            self.aliases
                .insert("default".to_string(), imported(&self.module, &named));
            self.exported.insert(named);
        }
        self.exporting = true;
        self.visit_export_default_declaration_kind(&item.declaration);
        self.exporting = false;
    }

    fn visit_export_all_declaration(&mut self, item: &ExportAllDeclaration<'ast>) {
        let located = self
            .specifiers
            .locate(&self.source.relative, &item.source.value);
        if let Located::Module(target) = &located {
            // A wholesale re-export names no symbol, so the module it reaches is remembered under
            // a key no identifier can spell and every unanswered lookup tries it.
            self.aliases.insert(format!("* {target}"), target.clone());
        }
        self.reached(&located, &[], item.span);
    }

    fn visit_class(&mut self, item: &Class<'ast>) {
        let Some(named) = item.id.as_ref().map(|held| held.name.to_string()) else {
            walk_class(self, item);
            return;
        };
        self.class(&named, item);
    }

    fn visit_function(&mut self, item: &Function<'ast>, flags: ScopeFlags) {
        let Some(named) = item.id.as_ref().map(|held| held.name.to_string()) else {
            walk_function(self, item, flags);
            return;
        };
        let mut declared = self.place(NodeKind::Function, &named, item.span, self.reach());
        declared.asynchronous = item.r#async;
        declared.return_annotation = item
            .return_type
            .as_ref()
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        let owner = self.declare(declared, item.span);
        self.signature(
            owner,
            item.type_parameters.as_deref(),
            &item.params,
            item.return_type.as_deref(),
            item.body.as_deref(),
        );
    }

    fn visit_method_definition(&mut self, item: &MethodDefinition<'ast>) {
        let Some(named) = key_name(&item.key) else {
            walk_method_definition(self, item);
            return;
        };
        if item.kind.is_constructor() {
            self.fields(item);
        }
        let kind = match item.kind.is_accessor() {
            true => NodeKind::Property,
            false => NodeKind::Method,
        };
        let reach = member_reach(&item.key, item.accessibility);
        let mut declared = self.place(kind, &named, item.span, reach);
        declared.asynchronous = item.value.r#async;
        declared.return_annotation = item
            .value
            .return_type
            .as_ref()
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        let owner = self.declare(declared, item.span);
        self.signature(
            owner,
            item.value.type_parameters.as_deref(),
            &item.value.params,
            item.value.return_type.as_deref(),
            item.value.body.as_deref(),
        );
    }

    fn visit_property_definition(&mut self, item: &PropertyDefinition<'ast>) {
        let Some(named) = key_name(&item.key) else {
            return;
        };
        let reach = member_reach(&item.key, item.accessibility);
        let mut declared = self.place(NodeKind::Attribute, &named, item.span, reach);
        declared.annotation = item
            .type_annotation
            .as_ref()
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        let owner = self.declare(declared, item.span);
        self.enter(owner);
        if let Some(annotation) = &item.type_annotation {
            self.visit_ts_type_annotation(annotation);
        }
        if let Some(value) = &item.value {
            self.visit_expression(value);
        }
        self.leave();
    }

    fn visit_accessor_property(&mut self, item: &AccessorProperty<'ast>) {
        let Some(named) = key_name(&item.key) else {
            return;
        };
        let reach = member_reach(&item.key, None);
        let mut declared = self.place(NodeKind::Property, &named, item.span, reach);
        declared.annotation = item
            .type_annotation
            .as_ref()
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        let owner = self.declare(declared, item.span);
        self.enter(owner);
        if let Some(value) = &item.value {
            self.visit_expression(value);
        }
        self.leave();
    }

    fn visit_ts_interface_declaration(&mut self, item: &TSInterfaceDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, true);
        for extended in &item.extends {
            if let Some(name) = expression_name(&extended.expression) {
                self.reference(&owner.id, &name, EdgeKind::Inherit, extended.span);
            }
        }
        self.signatures(owner, item.type_parameters.as_deref(), &item.body.body);
    }

    fn visit_ts_type_alias_declaration(&mut self, item: &TSTypeAliasDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, true);
        self.enter(owner);
        if let Some(generics) = &item.type_parameters {
            self.visit_ts_type_parameter_declaration(generics);
        }
        self.visit_ts_type(&item.type_annotation);
        self.leave();
    }

    fn visit_ts_enum_declaration(&mut self, item: &TSEnumDeclaration<'ast>) {
        let owner = self.datatype(&item.id.name, item.span, false);
        self.enter(owner);
        for member in &item.body.members {
            let named = match &member.id {
                oxc_ast::ast::TSEnumMemberName::Identifier(held) => held.name.to_string(),
                oxc_ast::ast::TSEnumMemberName::String(held)
                | oxc_ast::ast::TSEnumMemberName::ComputedString(held) => held.value.to_string(),
                oxc_ast::ast::TSEnumMemberName::ComputedTemplateString(_) => continue,
            };
            let declared =
                self.place(NodeKind::Attribute, &named, member.span, Visibility::Public);
            self.declare(declared, member.span);
        }
        self.leave();
    }

    fn visit_variable_declarator(&mut self, item: &VariableDeclarator<'ast>) {
        let Some(named) = item.id.get_identifier_name() else {
            walk_variable_declarator(self, item);
            return;
        };
        if let Some(annotation) = &item.type_annotation {
            self.visit_ts_type_annotation(annotation);
        }
        if self.bound_callable(&named, item) {
            return;
        }
        // A local binding names nothing another file could ever reach, so only what a module
        // states becomes a node and the rest is walked for what it calls.
        if self.owner().kind != NodeKind::Module {
            walk_variable_declarator(self, item);
            return;
        }
        let mut declared = self.place(NodeKind::Variable, &named, item.span, self.reach());
        declared.annotation = item
            .type_annotation
            .as_ref()
            .map(|annotation| self.rendered(annotation.type_annotation.span()));
        let owner = self.declare(declared, item.span);
        self.enter(owner);
        if let Some(value) = &item.init {
            self.visit_expression(value);
        }
        self.leave();
    }

    fn visit_call_expression(&mut self, item: &oxc_ast::ast::CallExpression<'ast>) {
        let owner = self.owner().id;
        if let Some(named) = expression_name(&item.callee) {
            self.reference(&owner, &named, EdgeKind::Call, item.span);
        }
        self.visit_expression(&item.callee);
        for argument in &item.arguments {
            self.visit_argument(argument);
        }
    }

    fn visit_new_expression(&mut self, item: &oxc_ast::ast::NewExpression<'ast>) {
        let owner = self.owner().id;
        if let Some(named) = expression_name(&item.callee) {
            self.reference(&owner, &named, EdgeKind::Instantiate, item.span);
        }
        for argument in &item.arguments {
            self.visit_argument(argument);
        }
    }

    fn visit_static_member_expression(
        &mut self,
        item: &oxc_ast::ast::StaticMemberExpression<'ast>,
    ) {
        let owner = self.owner().id;
        if let Some(named) = expression_name(&item.object) {
            let reached = format!("{named}.{}", item.property.name);
            self.reference(&owner, &reached, EdgeKind::Access, item.span);
        }
        self.visit_expression(&item.object);
    }

    fn visit_assignment_expression(&mut self, item: &AssignmentExpression<'ast>) {
        if let AssignmentTarget::StaticMemberExpression(held) = &item.left
            && matches!(held.object, Expression::ThisExpression(_))
            && let Some(holder) = self.classes.last().cloned()
        {
            let declared = node(
                Language::TypeScript,
                NodeKind::Attribute,
                &format!("{holder}.{}", held.property.name),
            );
            let target = declared.id.clone();
            let owner = identity(Language::TypeScript, NodeKind::Class, &holder);
            if self.placed.insert(target.clone()) {
                let mut declared = declared;
                declared.path = Some(self.source.relative.clone());
                declared.line = Some(self.line(item.span));
                self.nodes.push(declared);
                self.relate(&owner, &target, EdgeKind::Define, item.span);
            }
        }
        self.visit_assignment_target(&item.left);
        self.visit_expression(&item.right);
    }

    fn visit_ts_type_parameter(&mut self, item: &TSTypeParameter<'ast>) {
        self.generics.insert(item.name.name.to_string());
        walk_ts_type_parameter(self, item);
    }

    fn visit_ts_type_reference(&mut self, item: &TSTypeReference<'ast>) {
        let named = item.type_name.to_string();
        let head = named.split('.').next().unwrap_or_default();
        // A type parameter stands for whatever a caller supplies and `as const` names the value
        // rather than a type, so neither is a dependency on a declaration anything could reach.
        if !item.type_name.is_const() && !self.generics.contains(head) {
            let owner = self.owner().id;
            self.reference(&owner, &named, EdgeKind::Typed, item.span);
        }
        if let Some(arguments) = &item.type_arguments {
            self.visit_ts_type_parameter_instantiation(arguments);
        }
    }
}

/// Return the dotted name one expression reads as, when every step of it is a plain name.
fn expression_name(expression: &Expression<'_>) -> Option<String> {
    match expression {
        Expression::Identifier(held) => Some(held.name.to_string()),
        Expression::ThisExpression(_) => Some("this".to_string()),
        Expression::StaticMemberExpression(held) => Some(format!(
            "{}.{}",
            expression_name(&held.object)?,
            held.property.name
        )),
        Expression::PrivateFieldExpression(held) => Some(format!(
            "{}.#{}",
            expression_name(&held.object)?,
            held.field.name
        )),
        Expression::ParenthesizedExpression(held) => expression_name(&held.expression),
        Expression::TSNonNullExpression(held) => expression_name(&held.expression),
        Expression::TSAsExpression(held) => expression_name(&held.expression),
        _ => None,
    }
}

/// Return the name one class or interface member states, with the hash a private name is written with.
fn key_name(key: &PropertyKey<'_>) -> Option<String> {
    match key {
        PropertyKey::PrivateIdentifier(held) => Some(format!("#{}", held.name)),
        held => held.static_name().map(|name| name.to_string()),
    }
}

/// Return how widely one class member reaches, by the two ways this language states it.
fn member_reach(key: &PropertyKey<'_>, accessibility: Option<TSAccessibility>) -> Visibility {
    if matches!(key, PropertyKey::PrivateIdentifier(_)) {
        return Visibility::Private;
    }
    stated_reach(accessibility)
}

/// Return how widely one declaration reaches by the access modifier it carries.
fn stated_reach(accessibility: Option<TSAccessibility>) -> Visibility {
    match accessibility {
        Some(TSAccessibility::Private) => Visibility::Private,
        Some(TSAccessibility::Protected) => Visibility::Protected,
        _ => Visibility::Public,
    }
}

/// Resolve one TypeScript reference against the repository, leaving what cannot be proved visible.
///
/// An import arrives already settled against the file system, so what remains for it is following
/// what a module hands on until the one that actually declares the name. Every other reference is
/// a written name, which the bindings of its own module rewrite before the repository is asked.
pub fn resolve(
    reference: &Reference,
    modules: &BTreeSet<String>,
    symbols: &BTreeSet<String>,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let empty = BTreeMap::new();
    let local = aliases.get(&reference.module).unwrap_or(&empty);
    let mut candidates = Vec::new();
    if reference.kind == EdgeKind::Import {
        let (module, symbol) = split_import(&reference.expression);
        if !symbol.is_empty()
            && let Some(found) = declaring(module, symbol, aliases, symbols)
            && let Some((holder, _)) = found.rsplit_once('.')
            && modules.contains(holder)
        {
            candidates.push(holder.to_string());
        }
        candidates.push(module.to_string());
        if attach(reference, &candidates, modules, nodes, edges) {
            return;
        }
        stray(
            reference,
            NodeKind::UnresolvedSymbol,
            &format!("{}::{module}", reference.module),
            nodes,
            edges,
        );
        return;
    }
    let expanded = expand(&reference.expression, local);
    if let Some(holder) = &reference.owner
        && let Some(rest) = reference.expression.strip_prefix("this.")
    {
        candidates.push(format!("{holder}.{rest}"));
    }
    candidates.push(expanded.clone());
    if let Some((holder, name)) = expanded.rsplit_once('.') {
        candidates.extend(declaring(holder, name, aliases, symbols));
    }
    candidates.push(imported(&reference.module, &expanded));
    candidates.push(imported(&reference.module, &reference.expression));
    candidates.push(reference.expression.clone());
    if attach(reference, &candidates, symbols, nodes, edges) {
        return;
    }
    let head = reference.expression.split('.').next().unwrap_or_default();
    let (kind, qualname) = match is_provided(head) {
        true => (
            NodeKind::ExternalSymbol,
            format!("globalThis.{}", reference.expression),
        ),
        false => (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", reference.module, reference.expression),
        ),
    };
    stray(reference, kind, &qualname, nodes, edges);
}

/// Follow what one module hands on until the declaration that actually states the name.
///
/// A barrel that says `export { rule } from './decorators'` makes an import of `rule` reach the
/// module that writes it, and a dependency graph stopping at the barrel would point at a file
/// holding one line of re-export. The walk is bounded because a module re-exporting its own name
/// back would otherwise loop.
fn declaring(
    holder: &str,
    name: &str,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    symbols: &BTreeSet<String>,
) -> Option<String> {
    let mut current = imported(holder, name);
    for _ in 0..8 {
        if symbols.contains(&current) {
            return Some(current);
        }
        let (owner, symbol) = current.rsplit_once('.')?;
        let held = aliases.get(owner)?;
        let bound = match held.get(symbol) {
            Some(found) => found.clone(),
            None => starred(held, symbol, aliases, symbols)?,
        };
        if bound == current {
            return None;
        }
        current = bound;
    }
    None
}

/// Return where a wholesale re-export takes one name, when exactly one of them can hold it.
fn starred(
    held: &BTreeMap<String, String>,
    symbol: &str,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    symbols: &BTreeSet<String>,
) -> Option<String> {
    held.iter()
        .filter(|(key, _)| key.starts_with("* "))
        .map(|(_, target)| imported(target, symbol))
        .find(|candidate| {
            symbols.contains(candidate)
                || candidate
                    .rsplit_once('.')
                    .and_then(|(owner, name)| Some(aliases.get(owner)?.contains_key(name)))
                    .unwrap_or(false)
        })
}

/// Whether one name is something the language or its runtime provides.
///
/// Two sets meet here and both are outside this repository rather than missing from it. A runtime
/// global is what any host hands every program, and a utility type is what TypeScript itself
/// declares, so `Record<string, User>` depends on `User` and on nothing a project could edit.
fn is_provided(name: &str) -> bool {
    const NAMES: &[&str] = &[
        "Array",
        "ArrayBuffer",
        "AsyncGenerator",
        "AsyncIterable",
        "AsyncIterator",
        "Awaited",
        "BigInt",
        "Boolean",
        "Capitalize",
        "ConstructorParameters",
        "Date",
        "Error",
        "EvalError",
        "Exclude",
        "Extract",
        "FormData",
        "Function",
        "Generator",
        "Headers",
        "InstanceType",
        "Int8Array",
        "Int16Array",
        "Int32Array",
        "Intl",
        "Iterable",
        "Iterator",
        "JSON",
        "Lowercase",
        "Map",
        "Math",
        "NoInfer",
        "NonNullable",
        "Number",
        "Object",
        "Omit",
        "OmitThisParameter",
        "Parameters",
        "Partial",
        "Pick",
        "Promise",
        "PromiseLike",
        "Proxy",
        "RangeError",
        "ReadonlyArray",
        "ReadonlyMap",
        "ReadonlySet",
        "Record",
        "Reflect",
        "RegExp",
        "Request",
        "Required",
        "Response",
        "ReturnType",
        "Set",
        "SharedArrayBuffer",
        "String",
        "Symbol",
        "SyntaxError",
        "TextDecoder",
        "TextEncoder",
        "ThisParameterType",
        "ThisType",
        "TypeError",
        "URL",
        "URLSearchParams",
        "Uint8Array",
        "Uint16Array",
        "Uint32Array",
        "Uncapitalize",
        "Uppercase",
        "WeakMap",
        "WeakSet",
        "clearInterval",
        "clearTimeout",
        "console",
        "decodeURI",
        "decodeURIComponent",
        "encodeURI",
        "encodeURIComponent",
        "fetch",
        "globalThis",
        "isFinite",
        "isNaN",
        "parseFloat",
        "parseInt",
        "process",
        "queueMicrotask",
        "setInterval",
        "setTimeout",
        "structuredClone",
        "undefined",
    ];
    NAMES.contains(&name)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts_for(source: &str, family: &str) -> Vec<Value> {
        let document = Document {
            relative: "src/example.ts".to_string(),
            source: source.to_string(),
        };
        let mut facts = BTreeMap::from([(family.to_string(), Vec::new())]);
        extract(&document, &mut facts, &mut Stats::default());
        facts.remove(family).unwrap_or_default()
    }

    #[test]
    fn an_export_is_what_public_means_in_this_language() {
        let facts = facts_for(
            "export function build(name: string) {\n  return name;\n}\n\nfunction helper() {\n  return 1;\n}\n",
            "FunctionFact",
        );

        assert_eq!(facts.len(), 2);
        assert_eq!(facts[0]["name"], "build");
        assert_eq!(facts[0]["visibility"], "public");
        assert_eq!(facts[1]["visibility"], "internal");
    }

    #[test]
    fn a_class_carries_its_members_with_the_kinds_every_language_shares() {
        let facts = facts_for(
            "export class Engine extends Base {\n  limit = 3;\n\n  constructor() {\n    super();\n  }\n\n  run() {\n    return 1;\n  }\n\n  #secret() {\n    return 2;\n  }\n}\n",
            "ClassFact",
        );
        let classes = facts[0]["classes"].as_array().unwrap();

        assert_eq!(classes[0]["name"], "Engine");
        assert_eq!(classes[0]["visibility"], "public");
        assert_eq!(classes[0]["direct_bases"][0], "Base");
        assert_eq!(classes[0]["field_count"], 1);
        assert_eq!(classes[0]["methods"][0]["kind"], "constructor");
        let members = classes[0]["methods"].as_array().unwrap();
        assert!(
            members
                .iter()
                .any(|member| member["visibility"] == "private")
        );
    }

    #[test]
    fn an_import_records_whether_it_stays_inside_the_project() {
        let facts = facts_for(
            "import { User } from './models';\nimport React from 'react';\n\nconst value = User;\n",
            "ImportBindingFact",
        );

        assert_eq!(facts[0]["name"], "User");
        assert_eq!(facts[0]["is_relative"], true);
        assert_eq!(facts[0]["is_external"], false);
        assert_eq!(facts[1]["name"], "React");
        assert_eq!(facts[1]["is_external"], true);
    }

    #[test]
    fn a_module_counts_what_it_declares() {
        let facts = facts_for(
            "export class One {}\nclass Two {}\nexport function run() {}\n",
            "ModuleFact",
        );

        assert_eq!(facts[0]["class_count"], 2);
        assert_eq!(facts[0]["function_count"], 1);
    }

    #[test]
    fn a_private_member_is_private_however_the_class_spelled_it() {
        let facts = facts_for(
            "export class Engine {\n  #hidden() {}\n  private closed() {}\n  protected middle() {}\n  open() {}\n}\n",
            "FunctionFact",
        );
        let reach: Vec<&Value> = facts.iter().map(|fact| &fact["visibility"]).collect();

        assert_eq!(reach, ["private", "private", "protected", "public"]);
    }

    /// The shared vocabulary, the depth arithmetic, and the chain rule, all at once.
    ///
    /// The same program written for the reference frontend has to produce the same records, since
    /// the complexity and nesting rules own one scoring model for every language. A block a
    /// formatter added opens no structure and a nested callable states its own fact, so neither
    /// changes what this body scores.
    #[test]
    fn control_increments_record_their_nesting_depth() {
        let facts = facts_for(
            concat!(
                "export function run(items: number[][]): number {\n",
                "  for (const item of items) {\n",
                "    if (item.length) {\n",
                "      return 0;\n",
                "    } else if (item.length > 2) {\n",
                "      return 1;\n",
                "    } else {\n",
                "      return 2;\n",
                "    }\n",
                "  }\n",
                "  switch (items.length) {\n",
                "    case 0:\n",
                "      break;\n",
                "    default:\n",
                "      break;\n",
                "  }\n",
                "  {\n",
                "    const held = (value: number) => (value > 0 ? 1 : 0);\n",
                "    return held(1);\n",
                "  }\n",
                "}\n",
            ),
            "FunctionFact",
        );
        let increments: Vec<(&str, i64)> = facts[0]["control_increments"]
            .as_array()
            .unwrap()
            .iter()
            .map(|held| {
                (
                    held["kind"].as_str().unwrap_or_default(),
                    held["nesting_depth"].as_i64().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(
            increments,
            vec![
                ("loop", 0),
                ("conditional", 1),
                ("alternative", 1),
                ("alternative", 1),
                ("switch", 0),
            ]
        );
        assert_eq!(facts[0]["conditional_count"], 1);
        assert_eq!(facts[0]["implementation_lines"], 19);
    }

    #[test]
    fn syntax_facts_carry_declarations_calls_bindings_and_discarded_values() {
        let facts = facts_for(
            concat!(
                "export class Loader {\n",
                "  load(name: string): number {\n",
                "    const d = name.length;\n",
                "    if (d > 0) { console.log(d); debugger; }\n",
                "    name.length;\n",
                "    d === 3;\n",
                "    return d;\n",
                "  }\n",
                "}\n",
                "const trace = () => { console.debug(1); };\n"
            ),
            "SyntaxFact",
        );
        let named: Vec<&str> = facts
            .iter()
            .map(|fact| fact["qualname"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(named, vec!["Loader", "Loader.load", "trace"]);
        assert_eq!(facts[0]["tree"]["children"][0]["kind"], "callable");
        assert!(
            facts[0]["tree"]["children"][0]["children"]
                .as_array()
                .is_some_and(Vec::is_empty)
        );
        let method = &facts[1]["tree"];
        let mut pending = vec![method];
        let mut nodes = Vec::new();
        while let Some(node) = pending.pop() {
            nodes.push((
                node["kind"].as_str().unwrap_or_default().to_string(),
                node["name"].as_str().unwrap_or_default().to_string(),
            ));
            pending.extend(node["children"].as_array().into_iter().flatten());
        }

        assert!(nodes.contains(&("binding".to_string(), "d".to_string())));
        assert!(nodes.contains(&("branch".to_string(), String::new())));
        assert!(nodes.contains(&("call".to_string(), "console.log".to_string())));
        assert!(nodes.contains(&("effect".to_string(), "debugger".to_string())));
        assert_eq!(nodes.iter().filter(|(kind, _)| kind == "effect").count(), 4);
        assert_eq!(
            facts[2]["tree"]["children"][0]["children"][0]["name"],
            "console.debug"
        );
    }

    /// A guard around a body is one structure and the body it protects is one level deeper.
    #[test]
    fn a_guard_and_the_body_it_protects_are_one_structure_and_one_level() {
        let facts = facts_for(
            concat!(
                "export class Engine {\n",
                "  load(name: string): number {\n",
                "    try {\n",
                "      while (name.length) {\n",
                "        return 1;\n",
                "      }\n",
                "    } catch {\n",
                "      return 0;\n",
                "    }\n",
                "    return 2;\n",
                "  }\n",
                "}\n",
            ),
            "FunctionFact",
        );
        let increments: Vec<(&str, i64)> = facts[0]["control_increments"]
            .as_array()
            .unwrap()
            .iter()
            .map(|held| {
                (
                    held["kind"].as_str().unwrap_or_default(),
                    held["nesting_depth"].as_i64().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(increments, vec![("catch", 0), ("loop", 1)]);
        assert_eq!(facts[0]["name"], "load");
    }

    /// Reading the tree is what tells a type assertion apart from the keyword renaming an import.
    #[test]
    fn an_escape_hatch_is_read_from_the_tree_rather_than_from_the_word_as() {
        let facts = facts_for(
            concat!(
                "import { User as Person } from './models';\n",
                "export { Person as Account };\n",
                "// held as text rather than as an assertion\n",
                "const KINDS = ['json', 'toml'] as const;\n",
                "const said = 'a as b';\n",
                "const held = Person as unknown;\n",
                "const width = (held as any).length!;\n",
                "// @ts-expect-error the shape is checked elsewhere\n",
                "const total: any = width;\n",
            ),
            "ModuleSurfaceFact",
        );
        let hatches: Vec<(&str, i64)> = facts[0]["escape_hatches"]
            .as_array()
            .unwrap()
            .iter()
            .map(|held| {
                (
                    held["kind"].as_str().unwrap_or_default(),
                    held["line"].as_i64().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(
            hatches,
            vec![
                ("assertion", 6),
                ("non_null", 7),
                ("assertion", 7),
                ("any", 7),
                ("ignore_comment", 8),
                ("any", 9),
            ]
        );
    }

    /// A declaration an export wraps generates exactly the JavaScript the bare one does.
    #[test]
    fn a_construct_stripping_cannot_erase_is_found_through_the_export_around_it() {
        let facts = facts_for(
            concat!(
                "export enum Status {\n  Active = 'ACTIVE',\n}\n",
                "enum Held {\n  Off = 'OFF',\n}\n",
                "export class Engine {\n  constructor(private limit: number) {}\n}\n",
            ),
            "ModuleSurfaceFact",
        );
        let found: Vec<(&str, &str)> = facts[0]["erasable_violations"]
            .as_array()
            .unwrap()
            .iter()
            .map(|held| {
                (
                    held["kind"].as_str().unwrap_or_default(),
                    held["name"].as_str().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(
            found,
            vec![
                ("enum", "Status"),
                ("enum", "Held"),
                ("parameter_property", "limit"),
            ]
        );
    }

    /// A wholesale re-export names the module it republishes, and a climb names its specifier.
    #[test]
    fn a_surface_names_what_it_republishes_and_how_far_it_reaches() {
        let facts = facts_for(
            concat!(
                "export * from './UserService';\n",
                "export { User } from '../../models/user';\n",
                "import { Held } from '../held';\n",
            ),
            "ModuleSurfaceFact",
        );

        assert_eq!(facts[0]["star_reexport_count"], 1);
        assert_eq!(facts[0]["star_reexports"][0], "./UserService");
        assert_eq!(facts[0]["deepest_relative_import"], 2);
        assert_eq!(facts[0]["deepest_relative_specifier"], "../../models/user");
    }

    fn graph_of(sources: &[(&str, &str)]) -> crate::graph::Graph {
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        crate::graph::build("repo", &documents)
    }

    /// Return every symbol node the graph holds, leaving the places on disk out of it.
    fn symbols(graph: &crate::graph::Graph) -> Vec<String> {
        let mut found: Vec<String> = graph
            .nodes
            .iter()
            .filter(|node| !node.id.starts_with("path:"))
            .map(|node| node.id.clone())
            .collect();
        found.sort();
        found
    }

    /// Return every relation the graph states, leaving the containment of the tree out of it.
    fn relations(graph: &crate::graph::Graph) -> Vec<String> {
        let mut found: Vec<String> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind != EdgeKind::Contain)
            .map(|edge| format!("{} {:?} {}", edge.source, edge.kind, edge.target))
            .collect();
        found.sort();
        found.dedup();
        found
    }

    fn reaching(graph: &crate::graph::Graph, kind: EdgeKind) -> Vec<(&str, &str)> {
        let mut found: Vec<(&str, &str)> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == kind)
            .map(|edge| (edge.source.as_str(), edge.target.as_str()))
            .collect();
        found.sort_unstable();
        found.dedup();
        found
    }

    fn node_of<'a>(graph: &'a crate::graph::Graph, id: &str) -> &'a Node {
        graph
            .nodes
            .iter()
            .find(|node| node.id == id)
            .unwrap_or_else(|| panic!("the graph holds {id}"))
    }

    #[test]
    fn a_whole_small_project_produces_exactly_the_nodes_and_edges_written_out_by_hand() {
        let graph = graph_of(&[
            (
                "src/models.ts",
                "export interface Shape {\n  area: number;\n}\n\nexport class Circle implements Shape {\n  area = 1;\n}\n",
            ),
            (
                "src/main.ts",
                "import { Circle } from './models';\n\nexport function build(): Circle {\n  return new Circle();\n}\n",
            ),
        ]);

        assert_eq!(
            symbols(&graph),
            [
                "typescript:attribute:src/models.Circle.area",
                "typescript:attribute:src/models.Shape.area",
                "typescript:class:src/models.Circle",
                "typescript:class:src/models.Shape",
                "typescript:function:src/main.build",
                "typescript:module:src/main",
                "typescript:module:src/models",
            ]
        );
        assert_eq!(
            relations(&graph),
            [
                "path:file:src/main.ts Define typescript:module:src/main",
                "path:file:src/models.ts Define typescript:module:src/models",
                "typescript:class:src/models.Circle Define typescript:attribute:src/models.Circle.area",
                "typescript:class:src/models.Circle Inherit typescript:class:src/models.Shape",
                "typescript:class:src/models.Shape Define typescript:attribute:src/models.Shape.area",
                "typescript:function:src/main.build Instantiate typescript:class:src/models.Circle",
                "typescript:function:src/main.build Typed typescript:class:src/models.Circle",
                "typescript:module:src/main Access typescript:class:src/models.Circle",
                "typescript:module:src/main Define typescript:function:src/main.build",
                "typescript:module:src/main Import typescript:module:src/models",
                "typescript:module:src/models Define typescript:class:src/models.Circle",
                "typescript:module:src/models Define typescript:class:src/models.Shape",
            ]
        );
        assert!(
            graph
                .edges
                .iter()
                .all(|edge| edge.resolution == Resolution::Exact)
        );
    }

    #[test]
    fn a_contract_is_an_interface_an_abstract_class_or_an_alias_and_never_an_enum() {
        let graph = graph_of(&[(
            "src/shapes.ts",
            "export interface Reader {\n  read(): string;\n}\n\nexport abstract class Shape {}\n\nexport type Named = { name: string };\n\nexport enum Mode {\n  Fast,\n}\n\nexport class Circle extends Shape {}\n",
        )]);
        let stated: Vec<(&str, bool)> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Class)
            .map(|node| (node.qualname.as_str(), node.is_abstract))
            .collect();

        assert_eq!(
            stated,
            [
                ("src/shapes.Circle", false),
                ("src/shapes.Mode", false),
                ("src/shapes.Named", true),
                ("src/shapes.Reader", true),
                ("src/shapes.Shape", true),
            ]
        );
    }

    #[test]
    fn a_parameter_carries_how_it_binds_and_whether_a_caller_may_leave_it_out() {
        let graph = graph_of(&[(
            "src/run.ts",
            "export function run(first: string, second = 2, third?: number, ...rest: string[]) {\n  return first;\n}\n",
        )]);
        let mut stated: Vec<(&str, Option<ParameterKind>, bool, Option<usize>)> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Parameter)
            .map(|node| {
                (
                    node.qualname.as_str(),
                    node.parameter_kind,
                    node.has_default,
                    node.ordinal,
                )
            })
            .collect();
        stated.sort_by_key(|held| held.3);

        assert_eq!(
            stated,
            [
                (
                    "src/run.run.first",
                    Some(ParameterKind::PositionalOnly),
                    false,
                    Some(0)
                ),
                (
                    "src/run.run.second",
                    Some(ParameterKind::PositionalOnly),
                    true,
                    Some(1)
                ),
                (
                    "src/run.run.third",
                    Some(ParameterKind::PositionalOnly),
                    true,
                    Some(2)
                ),
                (
                    "src/run.run.rest",
                    Some(ParameterKind::VarPositional),
                    false,
                    Some(3)
                ),
            ]
        );
    }

    #[test]
    fn a_destructured_position_declares_no_name_and_still_holds_its_place() {
        let graph = graph_of(&[(
            "src/run.ts",
            "export function run({ left, right }: Pair, total: number) {\n  return total;\n}\n",
        )]);
        let stated: Vec<(&str, Option<usize>)> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Parameter)
            .map(|node| (node.qualname.as_str(), node.ordinal))
            .collect();

        assert_eq!(stated, [("src/run.run.total", Some(1))]);
    }

    #[test]
    fn visibility_reads_the_export_keyword_and_every_member_modifier() {
        let graph = graph_of(&[(
            "src/engine.ts",
            "export class Engine {\n  open = 1;\n  protected middle = 2;\n  private closed = 3;\n  #hidden = 4;\n}\n\nfunction helper() {}\n\nexport function shown() {}\n",
        )]);
        let mut stated: Vec<(&str, Visibility)> = graph
            .nodes
            .iter()
            .filter(|node| !node.id.starts_with("path:") && node.kind != NodeKind::Module)
            .map(|node| (node.qualname.as_str(), node.visibility))
            .collect();
        stated.sort_by_key(|held| held.0);

        assert_eq!(
            stated,
            [
                ("src/engine.Engine", Visibility::Public),
                ("src/engine.Engine.#hidden", Visibility::Private),
                ("src/engine.Engine.closed", Visibility::Private),
                ("src/engine.Engine.middle", Visibility::Protected),
                ("src/engine.Engine.open", Visibility::Public),
                ("src/engine.helper", Visibility::Internal),
                ("src/engine.shown", Visibility::Public),
            ]
        );
    }

    #[test]
    fn a_name_published_by_a_later_export_statement_still_reads_as_public() {
        let graph = graph_of(&[(
            "src/engine.ts",
            "function helper() {}\n\nexport { helper };\n",
        )]);

        assert_eq!(
            node_of(&graph, "typescript:function:src/engine.helper").visibility,
            Visibility::Public
        );
    }

    #[test]
    fn a_specifier_reaches_the_file_typescript_would_have_opened() {
        let graph = graph_of(&[
            (
                "src/main.ts",
                "import { helper } from './util';\nimport { thing } from './pack';\nimport { shape } from './shapes.js';\nimport { stated } from './ambient';\n",
            ),
            ("src/util.ts", "export const helper = 1;\n"),
            ("src/pack/index.ts", "export const thing = 1;\n"),
            ("src/shapes.ts", "export const shape = 1;\n"),
            ("src/ambient.d.ts", "export const stated = 1;\n"),
        ]);

        assert_eq!(
            reaching(&graph, EdgeKind::Import),
            [
                (
                    "typescript:module:src/main",
                    "typescript:module:src/ambient.d"
                ),
                (
                    "typescript:module:src/main",
                    "typescript:module:src/pack/index"
                ),
                ("typescript:module:src/main", "typescript:module:src/shapes"),
                ("typescript:module:src/main", "typescript:module:src/util"),
            ]
        );
    }

    #[test]
    fn an_import_of_a_reexported_symbol_reaches_what_defines_it() {
        let graph = graph_of(&[
            (
                "src/index.ts",
                "export { rule } from './decorators';\nexport * from './helpers';\n",
            ),
            ("src/decorators.ts", "export function rule() {}\n"),
            ("src/helpers.ts", "export function assist() {}\n"),
            (
                "src/api.ts",
                "import { rule, assist } from './index';\n\nexport function run() {\n  return rule() + assist();\n}\n",
            ),
        ]);
        let reached: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import && edge.path == "src/api.ts")
            .map(|edge| edge.target.as_str())
            .collect();

        assert_eq!(
            reached,
            [
                "typescript:module:src/decorators",
                "typescript:module:src/helpers"
            ]
        );
        assert!(reaching(&graph, EdgeKind::Call).contains(&(
            "typescript:function:src/api.run",
            "typescript:function:src/decorators.rule"
        )));
    }

    #[test]
    fn a_default_export_is_reached_under_whatever_name_the_importer_chose() {
        let graph = graph_of(&[
            ("src/widget.ts", "export default class Widget {}\n"),
            (
                "src/main.ts",
                "import Panel from './widget';\n\nexport function build() {\n  return new Panel();\n}\n",
            ),
        ]);

        assert!(reaching(&graph, EdgeKind::Instantiate).contains(&(
            "typescript:function:src/main.build",
            "typescript:class:src/widget.Widget"
        )));
        assert!(
            reaching(&graph, EdgeKind::Import)
                .contains(&("typescript:module:src/main", "typescript:module:src/widget"))
        );
    }

    #[test]
    fn a_binding_whose_value_is_a_callable_is_declared_as_one() {
        let graph = graph_of(&[(
            "src/load.ts",
            "export const load = async (event: string) => event.length;\n",
        )]);
        let declared = node_of(&graph, "typescript:function:src/load.load");

        assert!(declared.asynchronous);
        assert_eq!(declared.visibility, Visibility::Public);
        assert_eq!(
            node_of(&graph, "typescript:parameter:src/load.load.event").annotation,
            Some("string".to_string())
        );
    }

    #[test]
    fn a_receiver_written_as_this_reaches_the_member_of_its_own_class() {
        let graph = graph_of(&[(
            "src/engine.ts",
            "export class Engine {\n  limit = 1;\n\n  run() {\n    return this.size();\n  }\n\n  size() {\n    return this.limit;\n  }\n}\n",
        )]);

        assert!(reaching(&graph, EdgeKind::Call).contains(&(
            "typescript:method:src/engine.Engine.run",
            "typescript:method:src/engine.Engine.size"
        )));
        assert!(reaching(&graph, EdgeKind::Access).contains(&(
            "typescript:method:src/engine.Engine.size",
            "typescript:attribute:src/engine.Engine.limit"
        )));
    }

    #[test]
    fn a_package_this_repository_installs_is_a_dependency_rather_than_a_gap() {
        let graph = graph_of(&[(
            "src/schema.ts",
            "import { z } from 'zod';\nimport type { Handle } from '@sveltejs/kit';\n\nexport const shape = z.object();\n",
        )]);
        let outside: Vec<(&str, &str)> = graph
            .nodes
            .iter()
            .filter(|node| {
                matches!(
                    node.kind,
                    NodeKind::ExternalModule | NodeKind::ExternalSymbol
                )
            })
            .map(|node| (node.id.as_str(), node.qualname.as_str()))
            .collect();

        assert_eq!(
            outside,
            [
                ("typescript:external-module:@sveltejs/kit", "@sveltejs/kit"),
                ("typescript:external-module:zod", "zod"),
                (
                    "typescript:external-symbol:@sveltejs/kit.Handle",
                    "@sveltejs/kit.Handle"
                ),
                ("typescript:external-symbol:zod.z", "zod.z"),
                ("typescript:external-symbol:zod.z.object", "zod.z.object"),
            ]
        );
        assert!(
            graph
                .edges
                .iter()
                .filter(|edge| edge.target.contains(":external-"))
                .all(|edge| edge.resolution == Resolution::External)
        );
    }

    #[test]
    fn what_cannot_be_settled_stays_visible_rather_than_being_dropped() {
        let graph = graph_of(&[(
            "src/main.ts",
            "import Button from './Button.svelte';\n\nexport function run(handler) {\n  return handler(Button);\n}\n",
        )]);
        let gaps: Vec<&str> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::UnresolvedSymbol)
            .map(|node| node.qualname.as_str())
            .collect();

        assert_eq!(gaps, ["src/main::handler", "src/main::src/Button.svelte"]);
        assert!(
            graph
                .edges
                .iter()
                .filter(|edge| edge.target.contains(":unresolved-symbol:"))
                .all(|edge| edge.resolution == Resolution::Unresolved)
        );
    }

    #[test]
    fn a_type_parameter_is_a_binder_rather_than_a_dependency_on_anything() {
        let graph = graph_of(&[(
            "src/box.ts",
            "export interface Held {\n  size: number;\n}\n\nexport function unwrap<T extends Held>(held: T): T {\n  return held;\n}\n",
        )]);

        assert!(
            graph
                .nodes
                .iter()
                .all(|node| node.kind != NodeKind::UnresolvedSymbol)
        );
        assert!(reaching(&graph, EdgeKind::Typed).contains(&(
            "typescript:function:src/box.unwrap",
            "typescript:class:src/box.Held"
        )));
    }

    #[test]
    fn a_utility_type_the_language_declares_is_outside_this_repository() {
        let graph = graph_of(&[(
            "src/table.ts",
            "export interface Row {\n  id: string;\n}\n\nexport type Table = Record<string, Row>;\n",
        )]);
        let outside: Vec<&str> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::ExternalSymbol)
            .map(|node| node.qualname.as_str())
            .collect();

        assert_eq!(outside, ["globalThis.Record"]);
    }

    #[test]
    fn a_constructor_parameter_that_carries_a_modifier_declares_a_field_as_well() {
        let graph = graph_of(&[(
            "src/engine.ts",
            "export class Engine {\n  constructor(private readonly limit: number, plain: number) {\n    this.total = plain;\n  }\n}\n",
        )]);
        let held: Vec<(&str, Visibility)> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Attribute)
            .map(|node| (node.qualname.as_str(), node.visibility))
            .collect();

        assert_eq!(
            held,
            [
                ("src/engine.Engine.limit", Visibility::Private),
                ("src/engine.Engine.total", Visibility::Public),
            ]
        );
    }

    #[test]
    fn a_configured_alias_reaches_the_module_the_mapping_names() {
        let root = std::env::temp_dir().join(format!("mcmr-tsconfig-{}", std::process::id()));
        std::fs::create_dir_all(root.join("generated")).expect("the temporary root is writable");
        std::fs::write(
            root.join("tsconfig.json"),
            "{\n  // the framework writes the mapping\n  \"extends\": \"./generated/tsconfig.json\",\n  \"compilerOptions\": { \"strict\": true },\n}\n",
        )
        .expect("the file is writable");
        std::fs::write(
            root.join("generated/tsconfig.json"),
            "{\"compilerOptions\": {\"paths\": {\"$lib\": [\"../src/lib\"], \"$lib/*\": [\"../src/lib/*\"]}}}",
        )
        .expect("the file is writable");
        let documents = [
            Document {
                relative: "src/lib/models.ts".to_string(),
                source: "export class User {}\n".to_string(),
            },
            Document {
                relative: "src/lib/index.ts".to_string(),
                source: "export const version = 1;\n".to_string(),
            },
            Document {
                relative: "src/routes/page.ts".to_string(),
                source: "import { User } from '$lib/models';\nimport { version } from '$lib';\nimport { missing } from '$lib/generated/runtime';\n".to_string(),
            },
        ];
        let graph = crate::graph::build(&root.to_string_lossy(), &documents);
        std::fs::remove_dir_all(&root).expect("the temporary root is removable");
        let reached: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import)
            .map(|edge| edge.target.as_str())
            .collect();

        assert_eq!(
            reached,
            [
                "typescript:module:src/lib/models",
                "typescript:module:src/lib/index",
                "typescript:unresolved-symbol:src/routes/page::src/lib/generated/runtime",
            ]
        );
    }

    #[test]
    fn a_configuration_reads_through_the_comments_and_commas_json_forbids() {
        let read = plain_json(
            "{\n  // a line comment\n  \"paths\": {\n    /* a block comment */\n    \"$lib/*\": [\"../src/lib/*\"],\n  },\n  \"note\": \"http://not-a-comment\",\n}\n",
        );

        assert_eq!(
            read,
            "{\"paths\":{\"$lib/*\":[\"../src/lib/*\"]},\"note\":\"http://not-a-comment\"}"
        );
        assert!(serde_json::from_str::<Value>(&read).is_ok());
    }

    #[test]
    fn a_specifier_is_read_as_a_path_a_mapping_or_the_package_it_names() {
        let specifiers = Specifiers::of(
            "",
            BTreeSet::from(["src/lib/models".to_string(), "src/pack/index".to_string()]),
        );

        assert_eq!(
            specifiers.locate("src/main.ts", "./lib/models"),
            Located::Module("src/lib/models".to_string())
        );
        assert_eq!(
            specifiers.locate("src/lib/one.ts", "../pack"),
            Located::Module("src/pack/index".to_string())
        );
        assert_eq!(
            specifiers.locate("src/main.ts", "@scope/name/deep"),
            Located::Package("@scope/name".to_string())
        );
        assert_eq!(
            specifiers.locate("src/main.ts", "zod"),
            Located::Package("zod".to_string())
        );
        assert_eq!(
            specifiers.locate("src/main.ts", "./nowhere"),
            Located::Unsettled("src/nowhere".to_string())
        );
    }
}
