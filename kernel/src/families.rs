use crate::source::Source;
use crate::walk::{
    annotation_name, blocks, body_range, children, docstring, expressions, qualified_name, walk,
};
use ruff_python_ast::{Expr, ModModule, Parameters, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Every name one file binds, with the scope that binds it and the typing declarations it states.
///
/// Where a name is bound is what decides who can reach it, so a module constant, a class attribute
/// and a local all arrive named by their scope rather than folded together. Only a module-scope
/// name carries its references, since it is the only one this file can claim to have found every
/// use of, and finding them is a scan of the whole module per name.
pub fn symbols(source: &Source, module: &ModModule) -> Value {
    let reachable = names_are_reachable(module);
    let assignments: Vec<Value> = scoped_assignments(module)
        .into_iter()
        .map(|(scope, name, range)| {
            json!({
                "name": name.clone(),
                "scope": scope,
                "is_constant_assignment": name.chars().all(|letter| !letter.is_lowercase()),
                "returns_boolean": false,
                "reference": (scope == "module")
                    .then(|| bound(source, module, &name, range, reachable)),
            })
        })
        .collect();
    let predicates: Vec<Value> = module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item)
                if item.decorator_list.is_empty()
                    && item
                        .returns
                        .as_ref()
                        .is_some_and(|returns| annotation_name(returns) == "bool") =>
            {
                let name = item.name.to_string();
                Some(json!({
                    "name": name.clone(),
                    "scope": "module",
                    "returns_boolean": true,
                    "reference": bound(source, module, &name, item.name.range(), reachable),
                }))
            }
            _ => None,
        })
        .collect();
    let declared = [assignments, predicates].concat();
    json!({"symbols": declared, "typing_scopes": []})
}

/// Return every name one file binds by assignment, with the scope the binding sits in.
fn scoped_assignments(
    module: &ModModule,
) -> Vec<(&'static str, String, ruff_text_size::TextRange)> {
    let mut found = Vec::new();
    let mut pending: Vec<(&'static str, &Stmt)> = module
        .body
        .iter()
        .rev()
        .map(|held| ("module", held))
        .collect();
    while let Some((scope, statement)) = pending.pop() {
        let targets = match statement {
            Stmt::Assign(item) => item.targets.iter().collect::<Vec<_>>(),
            Stmt::AnnAssign(item) => vec![item.target.as_ref()],
            _ => Vec::new(),
        };
        found.extend(targets.into_iter().filter_map(|target| match target {
            Expr::Name(name) => Some((scope, name.id.to_string(), name.range())),
            _ => None,
        }));
        let inner = match statement {
            Stmt::ClassDef(_) => "class",
            Stmt::FunctionDef(_) => "local",
            _ => scope,
        };
        for block in blocks(statement) {
            pending.extend(block.iter().rev().map(|held| (inner, held)));
        }
    }
    found
}

/// Address one declaration together with every reference to it this file states.
///
/// A rename has to edit the declaration and every use together or not at all, so it needs both
/// addressed rather than counted. Whether these are *every* reference is a separate question, and
/// one this file alone can only answer for a name nothing outside it can see.
fn bound(
    source: &Source,
    module: &ModModule,
    name: &str,
    declaration: ruff_text_size::TextRange,
    reachable: bool,
) -> Value {
    let mut found = Vec::new();
    for statement in &module.body {
        collect_loads(source, statement, name, &mut found);
    }
    json!({
        "id": format!("{}:{name}", source.relative),
        "name": name,
        "declaration": source.node("name", declaration),
        "references": found,
        "are_references_complete": reachable && !name.starts_with("__"),
    })
}

fn collect_loads(source: &Source, statement: &Stmt, name: &str, found: &mut Vec<Value>) {
    for expression in expressions(statement) {
        collect_name_loads(source, expression, name, found);
    }
    for block in blocks(statement) {
        for held in block {
            collect_loads(source, held, name, found);
        }
    }
}

fn collect_name_loads(source: &Source, expression: &Expr, name: &str, found: &mut Vec<Value>) {
    if let Expr::Name(item) = expression
        && item.id.as_str() == name
        && item.ctx.is_load()
    {
        found.push(serde_json::to_value(source.node("name", item.range())).unwrap_or_default());
    }
    for child in children(expression) {
        collect_name_loads(source, child, name, found);
    }
}

/// Whether this file is the whole world for the names it declares privately.
///
/// A module-private name can only be reached from inside its own file, so reading the file reads
/// every reference. Two things break that. A name reached by string, through `getattr` or the
/// module dictionary, leaves no reference to find, and a re-export hands the name to callers this
/// file never sees. Where either appears, nothing here claims to have found everything.
fn names_are_reachable(module: &ModModule) -> bool {
    let mut reachable = true;
    for statement in &module.body {
        if let Stmt::Assign(item) = statement
            && item
                .targets
                .iter()
                .any(|target| matches!(target, Expr::Name(name) if name.id.as_str() == "__all__"))
        {
            reachable = false;
        }
        if names_dynamically(statement) {
            reachable = false;
        }
    }
    reachable
}

/// Whether one statement reaches a name by string rather than by writing it.
fn names_dynamically(statement: &Stmt) -> bool {
    const DYNAMIC: &[&str] = &["getattr", "setattr", "globals", "vars", "eval", "exec"];
    let named = expressions(statement)
        .into_iter()
        .flat_map(walk_expression)
        .any(|expression| {
            matches!(expression, Expr::Call(call)
                if DYNAMIC.contains(&qualified_name(&call.func).as_str()))
        });
    named
        || blocks(statement)
            .into_iter()
            .flatten()
            .any(names_dynamically)
}

/// Return one expression and every expression under it.
fn walk_expression(expression: &Expr) -> Vec<&Expr> {
    let mut found = vec![expression];
    for child in children(expression) {
        found.extend(walk_expression(child));
    }
    found
}

/// Every member access one file performs, with the visibility its spelling declares.
pub fn attribute_accesses(source: &Source, module: &ModModule) -> Value {
    let mut accesses = Vec::new();
    let enums = Enums::of(module);
    let bound = Bindings::of(None, &module.body, &enums);
    accessed(
        source,
        &module.body,
        None,
        &Scope { bound, enums },
        &mut accesses,
    );
    json!({"accesses": accesses})
}

/// What this file proved about the enumerations in reach of one scope.
struct Scope {
    bound: Bindings,
    enums: Enums,
}

/// Read one block's accesses, carrying the class whose body lexically encloses it.
///
/// The owning flag has to reach the accesses rather than the declaration that establishes it,
/// since every `self.x` a method writes sits in the method's body and never in the `def` line. A
/// nested callable keeps the class holding it and a nested class takes over, which is what the
/// innermost lexical owner means. A callable is also its own binding scope, so the names proven to
/// hold an enum member are rebuilt on the way into one and inherited everywhere else.
fn accessed(
    source: &Source,
    body: &[Stmt],
    owner: Option<&str>,
    scope: &Scope,
    accesses: &mut Vec<Value>,
) {
    for statement in body {
        for expression in stated(statement) {
            collect_accesses(source, expression, owner, scope, accesses);
        }
        let inner = match statement {
            Stmt::ClassDef(item) => Some(item.name.as_str()),
            _ => owner,
        };
        let opened = match statement {
            Stmt::FunctionDef(item) => Some(Scope {
                bound: Bindings::of(Some(&item.parameters), &item.body, &scope.enums),
                enums: scope.enums.clone(),
            }),
            _ => None,
        };
        for block in blocks(statement) {
            accessed(
                source,
                block,
                inner,
                opened.as_ref().unwrap_or(scope),
                accesses,
            );
        }
    }
}

fn collect_accesses(
    source: &Source,
    expression: &Expr,
    owner: Option<&str>,
    scope: &Scope,
    accesses: &mut Vec<Value>,
) {
    if let Expr::Attribute(item) = expression {
        let name = item.attr.to_string();
        let receiver = source.slice(item.value.range()).to_string();
        let kind = receiver_kind(&receiver, owner);
        let held = scope.bound.enum_of(&item.value, &scope.enums);
        accesses.push(json!({
            "name": name.clone(),
            "receiver_kind": kind,
            "visibility": member_visibility(&name),
            "is_inside_owning_class": owner.is_some() && kind != "other",
            "is_protocol_name": name.starts_with("__") && name.ends_with("__"),
            "receiver_text": receiver,
            "receiver_type": held.unwrap_or_default(),
            "receiver_type_bases": held.map(|name| scope.enums.bases(name)).unwrap_or_default(),
            "node": source.node_of("attribute", item),
        }));
    }
    for child in children(expression) {
        collect_accesses(source, child, owner, scope, accesses);
    }
}

fn receiver_kind(receiver: &str, owner: Option<&str>) -> &'static str {
    match receiver {
        "self" | "cls" => "self",
        "super()" => "super",
        _ if owner == Some(receiver) => "owner",
        _ => "other",
    }
}

fn member_visibility(name: &str) -> &'static str {
    if name.starts_with("__") && name.ends_with("__") {
        "public"
    } else if name.starts_with("__") {
        "private"
    } else if name.starts_with('_') {
        "protected"
    } else {
        "public"
    }
}

/// The enumerations one file declares, keyed by name, with the standard bases each derives.
///
/// A base is recorded under the name the standard `enum` module gives it, so a module writing
/// `from enum import StrEnum as Base` reaches the same answer as one writing it out. A class
/// stating its own `__str__` or `__int__` is left out entirely, because the conversion a rule
/// would recommend for it is no longer the one the standard base performs.
#[derive(Clone, Default)]
struct Enums {
    declared: BTreeMap<String, Vec<String>>,
}

impl Enums {
    fn of(module: &ModModule) -> Self {
        let aliases = enum_aliases(module);
        let declared = walk(module)
            .into_iter()
            .filter_map(|statement| match statement {
                Stmt::ClassDef(item) => Some(item),
                _ => None,
            })
            .filter(|item| !states_own_conversion(item))
            .filter_map(|item| {
                let bases: Vec<String> = item
                    .arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter())
                    .map(|base| {
                        let written = qualified_name(base);
                        let tail = written.rsplit('.').next().unwrap_or(&written).to_string();
                        aliases.get(&tail).cloned().unwrap_or(tail)
                    })
                    .collect();
                enum_kind(&bases).map(|_| (item.name.to_string(), bases))
            })
            .collect();
        Self { declared }
    }

    fn holds(&self, name: &str) -> bool {
        self.declared.contains_key(name)
    }

    fn bases(&self, name: &str) -> Vec<String> {
        self.declared.get(name).cloned().unwrap_or_default()
    }
}

/// Return what each name a module imports from `enum` is called in the standard module.
fn enum_aliases(module: &ModModule) -> BTreeMap<String, String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ImportFrom(item)
                if item.level == 0
                    && item
                        .module
                        .as_ref()
                        .is_some_and(|name| name.as_str() == "enum") =>
            {
                Some(item)
            }
            _ => None,
        })
        .flat_map(|item| item.names.iter())
        .filter_map(|alias| {
            alias
                .asname
                .as_ref()
                .map(|bound| (bound.to_string(), alias.name.to_string()))
        })
        .collect()
}

/// Whether one class replaces the conversion its standard enum base would otherwise perform.
fn states_own_conversion(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.body.iter().any(|member| {
        matches!(member, Stmt::FunctionDef(method)
            if matches!(method.name.as_str(), "__str__" | "__int__"))
    })
}

/// The names one scope binds exactly once to a value whose enumeration this file states.
///
/// Binding a name twice is what makes it ambiguous, so every binding is counted and only the names
/// bound once survive. That is the whole of the proof, and a name reached any other way stays
/// unknown rather than being guessed at from its spelling.
#[derive(Default)]
struct Bindings {
    names: BTreeMap<String, String>,
}

impl Bindings {
    fn of(parameters: Option<&Parameters>, body: &[Stmt], enums: &Enums) -> Self {
        let mut counted: BTreeMap<String, usize> = BTreeMap::new();
        let mut proven: BTreeMap<String, String> = BTreeMap::new();
        let annotated = parameters
            .into_iter()
            .flat_map(|held| held.iter())
            .map(|item| {
                let named = item
                    .annotation()
                    .map(annotation_name)
                    .filter(|held| enums.holds(held));
                (item.name().to_string(), named)
            });
        for (name, held) in annotated.chain(scope_bindings(body, enums)) {
            *counted.entry(name.clone()).or_default() += 1;
            if let Some(class) = held {
                proven.insert(name, class);
            }
        }
        Self {
            names: proven
                .into_iter()
                .filter(|(name, _)| counted.get(name) == Some(&1))
                .collect(),
        }
    }

    /// Return the enumeration one receiver expression is proven to be a member of.
    fn enum_of<'enums>(&self, receiver: &Expr, enums: &'enums Enums) -> Option<&'enums str> {
        let named = match receiver {
            Expr::Name(item) => self.names.get(item.id.as_str()).cloned(),
            Expr::Attribute(item) => Some(qualified_name(&item.value)),
            Expr::Call(item) => Some(qualified_name(&item.func)),
            Expr::Subscript(item) => Some(qualified_name(&item.value)),
            _ => None,
        }?;
        enums
            .declared
            .get_key_value(named.as_str())
            .map(|(held, _)| held.as_str())
    }
}

/// Return every name one scope binds, with the enumeration the binding proves where it proves one.
fn scope_bindings(body: &[Stmt], enums: &Enums) -> Vec<(String, Option<String>)> {
    let mut found = Vec::new();
    for statement in owned(body) {
        match statement {
            Stmt::Assign(item) => found.extend(
                item.targets
                    .iter()
                    .map(|target| (bound_name(target), member_of(&item.value, enums))),
            ),
            Stmt::AnnAssign(item) => found.push((
                bound_name(&item.target),
                Some(annotation_name(&item.annotation)).filter(|held| enums.holds(held)),
            )),
            Stmt::For(item) => found.push((bound_name(&item.target), iterated(&item.iter, enums))),
            Stmt::AugAssign(item) => found.push((bound_name(&item.target), None)),
            Stmt::With(item) => found.extend(
                item.items
                    .iter()
                    .filter_map(|entry| entry.optional_vars.as_deref())
                    .map(|target| (bound_name(target), None)),
            ),
            _ => {}
        }
        for expression in stated(statement) {
            comprehension_bindings(expression, enums, &mut found);
        }
    }
    found.retain(|(name, _)| !name.is_empty());
    found
}

fn comprehension_bindings(
    expression: &Expr,
    enums: &Enums,
    found: &mut Vec<(String, Option<String>)>,
) {
    for generator in comprehension_clauses(expression) {
        found.push((
            bound_name(&generator.target),
            iterated(&generator.iter, enums),
        ));
    }
    for child in children(expression) {
        comprehension_bindings(child, enums, found);
    }
}

fn bound_name(target: &Expr) -> String {
    match target {
        Expr::Name(item) => item.id.to_string(),
        _ => String::new(),
    }
}

/// Return the enumeration one value expression proves its name holds a member of.
fn member_of(value: &Expr, enums: &Enums) -> Option<String> {
    let named = match value {
        Expr::Attribute(item) => qualified_name(&item.value),
        Expr::Call(item) => qualified_name(&item.func),
        Expr::Subscript(item) => qualified_name(&item.value),
        _ => return None,
    };
    enums.holds(&named).then_some(named)
}

/// Return the enumeration one loop proves its target holds a member of.
fn iterated(iterable: &Expr, enums: &Enums) -> Option<String> {
    let named = qualified_name(iterable);
    enums.holds(&named).then_some(named)
}

/// Every resolved annotation one file declares, with the union members it names.
pub fn annotations(source: &Source, module: &ModModule) -> Value {
    let declared: Vec<Value> = walk(module)
        .into_iter()
        .flat_map(annotation_expressions)
        .map(|annotation| {
            json!({
                "path": source.relative.clone(),
                "union_members": union_members(annotation),
                "resolved_names": [annotation_name(annotation)],
                "constraint_recipe": source.slice(annotation.range()),
                "is_field_specific_metadata": describes_one_field(annotation),
            })
        })
        .collect();
    json!({"annotations": declared})
}

/// Whether one annotation carries metadata that belongs to the single field declaring it.
///
/// A constraint travels to every field that needs the same shape, while a description, a title, an
/// alias, or an example is written about one field and reads as noise anywhere else. Grouping the
/// two together would propose an alias for a recipe nobody else can reuse.
fn describes_one_field(annotation: &Expr) -> bool {
    const DESCRIBING: &[&str] = &[
        "description",
        "title",
        "alias",
        "validation_alias",
        "serialization_alias",
        "examples",
        "json_schema_extra",
        "deprecated",
    ];
    let mut pending = vec![annotation];
    while let Some(expression) = pending.pop() {
        if let Expr::Call(item) = expression
            && item.arguments.keywords.iter().any(|keyword| {
                keyword
                    .arg
                    .as_ref()
                    .is_some_and(|named| DESCRIBING.contains(&named.as_str()))
            })
        {
            return true;
        }
        pending.extend(children(expression));
    }
    false
}

fn annotation_expressions(statement: &Stmt) -> Vec<&Expr> {
    match statement {
        Stmt::AnnAssign(item) => vec![item.annotation.as_ref()],
        Stmt::FunctionDef(item) => item
            .returns
            .iter()
            .map(AsRef::as_ref)
            .chain(
                item.parameters
                    .iter()
                    .filter_map(|parameter| parameter.annotation()),
            )
            .collect(),
        _ => Vec::new(),
    }
}

fn union_members(annotation: &Expr) -> Vec<String> {
    match annotation {
        Expr::BinOp(item) => [union_members(&item.left), union_members(&item.right)].concat(),
        _ => vec![annotation_name(annotation)],
    }
}

/// Every try statement one file protects, with the sizes of its clauses.
pub fn try_blocks(source: &Source, module: &ModModule) -> Value {
    let regions: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::Try(item) => Some(json!({
                "leading_literal_assignment_count": item
                    .body
                    .iter()
                    .take_while(|entry| is_literal_assignment(entry))
                    .count(),
                "has_following_raising_operation": item
                    .body
                    .iter()
                    .any(|entry| !is_literal_assignment(entry)),
                "clause_statement_counts": item
                    .handlers
                    .iter()
                    .map(|handler| {
                        let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
                        clause.body.len()
                    })
                    .collect::<Vec<_>>(),
                "statement": source.node_of("try", statement),
                "leading_assignments": item
                    .body
                    .iter()
                    .take_while(|entry| is_literal_assignment(entry))
                    .map(|entry| source.node_of("statement", entry))
                    .collect::<Vec<_>>(),
            })),
            _ => None,
        })
        .collect();
    json!({"regions": regions})
}

fn is_literal_assignment(statement: &Stmt) -> bool {
    match statement {
        Stmt::Assign(item) => is_literal(&item.value),
        Stmt::AnnAssign(item) => item.value.as_ref().is_some_and(|value| is_literal(value)),
        _ => false,
    }
}

fn is_literal(expression: &Expr) -> bool {
    matches!(
        expression,
        Expr::StringLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::List(_)
            | Expr::Tuple(_)
            | Expr::Dict(_)
            | Expr::Set(_)
    )
}

/// Every comprehension one file writes and every loop that fills a set by hand.
pub fn comprehensions(source: &Source, module: &ModModule) -> Value {
    let mut counts = Vec::new();
    for statement in walk(module) {
        for expression in expressions(statement) {
            collect_comprehensions(expression, &mut counts);
        }
    }
    json!({"loop_counts": counts, "set_loop_candidates": set_loops(source, module)})
}

fn collect_comprehensions(expression: &Expr, counts: &mut Vec<usize>) {
    let generators = match expression {
        Expr::ListComp(item) => Some(item.generators.len()),
        Expr::SetComp(item) => Some(item.generators.len()),
        Expr::DictComp(item) => Some(item.generators.len()),
        Expr::Generator(item) => Some(item.generators.len()),
        _ => None,
    };
    if let Some(count) = generators {
        counts.push(count);
    }
    for child in children(expression) {
        collect_comprehensions(child, counts);
    }
}

fn set_loops(source: &Source, module: &ModModule) -> Vec<Value> {
    let mut candidates = Vec::new();
    for statement in walk(module) {
        for block in blocks(statement) {
            candidates.extend(set_loops_in(source, block));
        }
    }
    candidates.extend(set_loops_in(source, &module.body));
    candidates
}

fn set_loops_in(source: &Source, body: &[Stmt]) -> Vec<Value> {
    body.windows(2)
        .filter_map(|pair| {
            let (Stmt::Assign(initialization), Stmt::For(loop_statement)) = (&pair[0], &pair[1])
            else {
                return None;
            };
            let name = match initialization.targets.first()? {
                Expr::Name(name) => name.id.to_string(),
                _ => return None,
            };
            if !is_empty_set(&initialization.value) {
                return None;
            }
            let addition = single_addition(&loop_statement.body, &name)?;
            Some(json!({
                "name": name,
                "has_unshadowed_set_initialization": true,
                "loop_is_synchronous": !loop_statement.is_async,
                "only_effect_is_add": true,
                "conditional_count": 0,
                "has_else": !loop_statement.orelse.is_empty(),
                "initialization": source.node_of("statement", &pair[0]),
                "loop": source.node_of("statement", &pair[1]),
                "element": source.node("expression", addition),
                "target": source.node("expression", loop_statement.target.range()),
                "iterable": source.node("expression", loop_statement.iter.range()),
                "conditions": [],
            }))
        })
        .collect()
}

fn is_empty_set(value: &Expr) -> bool {
    matches!(value, Expr::Call(call)
        if qualified_name(&call.func) == "set" && call.arguments.args.is_empty())
}

/// Return where one loop body adds its single element, when adding is all it does.
///
/// The caller wants the place rather than the expression, and handing back the range instead of a
/// borrow of the tree is what keeps the borrow out of the signature.
fn single_addition(body: &[Stmt], name: &str) -> Option<ruff_text_size::TextRange> {
    let [Stmt::Expr(statement)] = body else {
        return None;
    };
    let Expr::Call(call) = statement.value.as_ref() else {
        return None;
    };
    if qualified_name(&call.func) != format!("{name}.add") || call.arguments.args.len() != 1 {
        return None;
    }
    call.arguments.args.first().map(Ranged::range)
}

/// Every local literal collection one file builds, with the reads that fix its representation.
///
/// A representation is interchangeable only where every read of the binding proves it, so this
/// reads one callable at a time. A module constant is not a candidate at all, because its readers
/// are every file that imports it and this file cannot see them.
pub fn collections(source: &Source, module: &ModModule) -> Value {
    let bodies: Vec<&[Stmt]> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => Some(item.body.as_slice()),
            _ => None,
        })
        .collect();
    json!({
        "pair_sequences": bodies
            .iter()
            .flat_map(|body| pair_sequences(source, body))
            .collect::<Vec<_>>(),
        "local_collections": bodies
            .iter()
            .flat_map(|body| local_collections(source, body))
            .collect::<Vec<_>>(),
    })
}

/// Return the fixed pair tables one callable body binds, with the reads that fix their shape.
///
/// A table of pairs whose every read looks one key up is a dictionary written as a sequence, and
/// the proof is the same one a representation needs, which is every read of a name one body binds.
fn pair_sequences(source: &Source, body: &[Stmt]) -> Vec<Value> {
    let statements = owned(body);
    statements
        .iter()
        .filter_map(|statement| {
            let Stmt::Assign(item) = statement else {
                return None;
            };
            let [Expr::Name(target)] = item.targets.as_slice() else {
                return None;
            };
            let elements = match item.value.as_ref() {
                Expr::List(list) => &list.elts,
                Expr::Tuple(tuple) => &tuple.elts,
                _ => return None,
            };
            let keys: Vec<&Expr> = elements.iter().filter_map(pair_key).collect();
            if keys.is_empty() || keys.len() != elements.len() {
                return None;
            }
            let reads = Reads::of(&statements, target.id.as_str());
            let kinds: Vec<Option<&str>> = keys.iter().map(|key| literal_kind(key)).collect();
            let texts: Vec<&str> = keys.iter().map(|key| source.slice(key.range())).collect();
            Some(json!({
                "pair_count": elements.len(),
                "keys_are_unique_literals": kinds
                    .iter()
                    .all(|held| *held == kinds[0] && held.is_some())
                    && texts.iter().collect::<BTreeSet<_>>().len() == texts.len(),
                "has_single_assignment": reads.stores == 1,
                "all_reads_are_lookup_loops": reads.loads > 0 && reads.loads == reads.lookup,
            }))
        })
        .collect()
}

/// Return the key one element states, when the element is a pair the source writes out.
fn pair_key(element: &Expr) -> Option<&Expr> {
    match element {
        Expr::Tuple(item) if item.elts.len() == 2 => item.elts.first(),
        _ => None,
    }
}

/// Whether one loop does nothing but hand back the value sitting beside a key it matched.
///
/// That is the shape a dictionary lookup replaces exactly. A loop comparing the key twice, running
/// anything after the branch, or falling through to an `else` is doing something a mapping does
/// not, so it leaves the sequence alone.
fn is_lookup_loop(item: &ruff_python_ast::StmtFor) -> bool {
    let Expr::Tuple(target) = item.target.as_ref() else {
        return false;
    };
    let [Expr::Name(key), Expr::Name(value)] = target.elts.as_slice() else {
        return false;
    };
    let [Stmt::If(branch)] = item.body.as_slice() else {
        return false;
    };
    let Expr::Compare(test) = branch.test.as_ref() else {
        return false;
    };
    if !branch.elif_else_clauses.is_empty()
        || !item.orelse.is_empty()
        || !matches!(test.ops.as_ref(), [ruff_python_ast::CmpOp::Eq])
        || !is_named(&test.left, key.id.as_str())
    {
        return false;
    }
    matches!(branch.body.as_slice(), [Stmt::Return(held)]
        if held.value.as_deref().is_some_and(|held| is_named(held, value.id.as_str())))
}

/// Return the local literal collections one callable body binds exactly once.
fn local_collections(source: &Source, body: &[Stmt]) -> Vec<Value> {
    let statements = owned(body);
    statements
        .iter()
        .filter_map(|statement| {
            let Stmt::Assign(item) = statement else {
                return None;
            };
            let [Expr::Name(target)] = item.targets.as_slice() else {
                return None;
            };
            let (kind, elements) = match item.value.as_ref() {
                Expr::List(list) => ("list", &list.elts),
                Expr::Tuple(tuple) => ("tuple", &tuple.elts),
                _ => return None,
            };
            let name = target.id.as_str();
            let reads = Reads::of(&statements, name);
            if reads.stores != 1 {
                return None;
            }
            let texts: Vec<&str> = elements
                .iter()
                .map(|element| source.slice(element.range()))
                .collect();
            let kinds: Vec<Option<&str>> = elements.iter().map(|e| literal_kind(e)).collect();
            Some(json!({
                "name": name,
                "kind": kind,
                "value_count": elements.len(),
                "has_homogeneous_literals": !kinds.is_empty()
                    && kinds.iter().all(|held| *held == kinds[0] && held.is_some()),
                "all_reads_are_iteration": reads.loads > 0 && reads.loads == reads.iteration,
                "all_reads_are_membership": reads.loads > 0 && reads.loads == reads.membership,
                "values_are_unique": texts.iter().collect::<BTreeSet<_>>().len()
                    == texts.len(),
            }))
        })
        .collect()
}

/// How one callable uses a name it binds, counted by the shapes that fix a representation.
///
/// A load neither iterated over nor tested for membership is representation sensitive, whichever
/// shape it takes, so counting the two provable shapes against every load is what lets a rule
/// abstain on indexing, unpacking, mutation, and everything else without naming any of them. A
/// lookup loop is a third and narrower shape, since every one of them is also an iteration.
#[derive(Default)]
struct Reads {
    stores: usize,
    loads: usize,
    iteration: usize,
    membership: usize,
    lookup: usize,
}

impl Reads {
    fn of(statements: &[&Stmt], name: &str) -> Self {
        let mut counted = Self::default();
        for statement in statements {
            if let Stmt::For(item) = statement
                && is_named(&item.iter, name)
            {
                counted.iteration += 1;
                counted.lookup += usize::from(is_lookup_loop(item));
            }
            for expression in stated(statement) {
                counted.count(expression, name);
            }
        }
        counted
    }

    fn count(&mut self, expression: &Expr, name: &str) {
        match expression {
            Expr::Name(item) if item.id.as_str() == name && item.ctx.is_load() => self.loads += 1,
            Expr::Name(item) if item.id.as_str() == name => self.stores += 1,
            Expr::Compare(item)
                if is_membership(&item.ops)
                    && matches!(item.comparators.as_ref(), [held] if is_named(held, name)) =>
            {
                self.membership += 1;
            }
            _ => {
                for generator in comprehension_clauses(expression) {
                    if is_named(&generator.iter, name) {
                        self.iteration += 1;
                    }
                }
            }
        }
        for child in children(expression) {
            self.count(child, name);
        }
    }
}

fn is_named(expression: &Expr, name: &str) -> bool {
    matches!(expression, Expr::Name(item) if item.id.as_str() == name)
}

/// Whether one comparison asks for membership rather than any other relation.
fn is_membership(operators: &[ruff_python_ast::CmpOp]) -> bool {
    use ruff_python_ast::CmpOp;
    matches!(operators, [CmpOp::In] | [CmpOp::NotIn]) // codespell:ignore
}

fn comprehension_clauses(expression: &Expr) -> &[ruff_python_ast::Comprehension] {
    match expression {
        Expr::ListComp(item) => &item.generators,
        Expr::SetComp(item) => &item.generators,
        Expr::DictComp(item) => &item.generators,
        Expr::Generator(item) => &item.generators,
        _ => &[],
    }
}

/// Return every statement one callable owns, stopping at a nested declaration's own body.
///
/// A nested function is a scope of its own, so the names it binds and reads answer for it rather
/// than for the callable holding it, and `walk` reaches that body separately.
fn owned(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        if matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            continue;
        }
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Return every expression one statement holds, including the targets it binds.
///
/// `expressions` answers what a statement evaluates, which deliberately leaves out what it assigns
/// to. Counting how often a name is bound needs both sides.
fn stated(statement: &Stmt) -> Vec<&Expr> {
    let mut found = expressions(statement);
    match statement {
        Stmt::Assign(item) => found.extend(item.targets.iter()),
        Stmt::AnnAssign(item) => found.push(item.target.as_ref()),
        Stmt::AugAssign(item) => found.push(item.target.as_ref()),
        Stmt::With(item) => found.extend(
            item.items
                .iter()
                .filter_map(|entry| entry.optional_vars.as_deref()),
        ),
        _ => {}
    }
    found
}

/// Name the shape one expression carries when the source states it literally.
fn literal_kind(expression: &Expr) -> Option<&'static str> {
    match expression {
        Expr::StringLiteral(_) => Some("string"),
        Expr::NumberLiteral(_) => Some("number"),
        Expr::BooleanLiteral(_) => Some("boolean"),
        Expr::NoneLiteral(_) => Some("none"),
        Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) => Some("sequence"),
        Expr::Dict(_) => Some("mapping"),
        _ => None,
    }
}

/// Every string expression one file folds together, and the separators it draws.
pub fn strings(source: &Source, module: &ModModule) -> Value {
    let mut expressions_found = Vec::new();
    for statement in walk(module) {
        for expression in expressions(statement) {
            collect_strings(source, expression, &mut expressions_found);
        }
    }
    json!({"expressions": expressions_found})
}

fn collect_strings(source: &Source, expression: &Expr, found: &mut Vec<Value>) {
    if let Expr::StringLiteral(item) = expression {
        let value = item.value.to_str().to_string();
        let repeated = repeated_unit(&value);
        found.push(json!({
            "runtime_value": value.clone(),
            "node": source.node_of("string", item),
            "literal_fragment_count": item.value.as_slice().len().max(1),
            "wraps_single_runtime_line": !value.contains('\n'),
            "repeated_literal": repeated.clone().unwrap_or_default(),
            "repetition_count": repeated
                .map(|unit| value.len() / unit.len().max(1))
                .unwrap_or(0),
        }));
    }
    for child in children(expression) {
        collect_strings(source, child, found);
    }
}

/// Return the single character one string repeats, when it is nothing else.
fn repeated_unit(value: &str) -> Option<String> {
    let first = value.chars().next()?;
    if value.len() < 4 || first.is_alphanumeric() || !value.chars().all(|letter| letter == first) {
        return None;
    }
    Some(first.to_string())
}

/// Every isinstance check one file makes, with the operations the block it guards performs.
///
/// What a check stands in for is only visible in what it protects, so the guarded block travels
/// with it. A check written anywhere but a branch test guards nothing this file can point at, and
/// says so by naming no operation rather than by being left out.
pub fn runtime_checks(module: &ModModule) -> Value {
    let mut checks = Vec::new();
    for statement in walk(module) {
        match statement {
            Stmt::If(item) => {
                let guarded = Guard {
                    body: &item.body,
                    alone: item.body.len() == 1 && item.elif_else_clauses.is_empty(),
                };
                collect_checks(&item.test, Some(&guarded), &mut checks);
            }
            _ => {
                for expression in expressions(statement) {
                    collect_checks(expression, None, &mut checks);
                }
            }
        }
    }
    json!({"checks": checks})
}

/// The block one branch protects, and whether protecting it is all the branch does.
struct Guard<'source> {
    body: &'source [Stmt],
    alone: bool,
}

fn collect_checks(expression: &Expr, guard: Option<&Guard>, checks: &mut Vec<Value>) {
    if let Expr::Call(item) = expression
        && qualified_name(&item.func) == "isinstance"
        && item.arguments.args.len() == 2
    {
        let subject = qualified_name(&item.arguments.args[0]);
        let performed = guard
            .map(|held| guarded_operations(held.body, &subject))
            .unwrap_or_default();
        checks.push(json!({
            "concrete_type": qualified_name(&item.arguments.args[1]),
            "guarded_operations": performed,
            "can_use_eafp": guard.is_some_and(|held| held.alone),
        }));
    }
    for child in children(expression) {
        collect_checks(child, guard, checks);
    }
}

/// Return the operations one guarded block performs on the value the check narrowed.
fn guarded_operations(body: &[Stmt], subject: &str) -> Vec<String> {
    let mut uses = Uses::default();
    uses.read_body(body, subject);
    let mut found: Vec<String> = uses.operations.into_iter().collect();
    found.extend(uses.attributes);
    found.sort();
    found.dedup();
    found
}

/// Every chain of conditions one file tests in sequence against one subject.
pub fn branches(source: &Source, module: &ModModule) -> Value {
    let chains: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::If(item) => conditional_chain(source, statement, item),
            _ => None,
        })
        .collect();
    json!({"chains": chains})
}

fn conditional_chain(
    source: &Source,
    statement: &Stmt,
    item: &ruff_python_ast::StmtIf,
) -> Option<Value> {
    let (subject, first) = subject_arm(&item.test, &item.body)?;
    let mut arms = vec![first];
    let mut fallback = false;
    for clause in &item.elif_else_clauses {
        match clause.test.as_ref() {
            Some(test) => arms.push(match subject_arm(test, &clause.body) {
                Some((named, arm)) if named == subject => arm,
                _ => wider_arm(&clause.body),
            }),
            None => fallback = true,
        }
    }
    Some(json!({
        "subject": subject,
        "arms": arms,
        "has_fallback": fallback,
        "node": source.node_of("if", statement),
    }))
}

/// Return the subject and arm one test declares, when it compares that subject to a literal.
///
/// The body travels with the test because what an arm does is half of what makes a chain
/// replaceable. A chain whose every arm hands back a value is a table written as control flow,
/// while one whose arms run several statements each is branching that happens to key on a literal.
fn subject_arm(test: &Expr, body: &[Stmt]) -> Option<(String, Value)> {
    let Expr::Compare(compare) = test else {
        return None;
    };
    let [operator] = compare.ops.as_ref() else {
        return None;
    };
    let [comparator] = compare.comparators.as_ref() else {
        return None;
    };
    let subject = qualified_name(&compare.left);
    if subject.is_empty() || !is_literal(comparator) {
        return None;
    }
    Some((
        subject,
        arm(
            comparison_name(operator),
            literal_text(comparator),
            body,
            true,
        ),
    ))
}

/// Return the arm one test declares when it reads more than the subject the chain keys on.
///
/// Such an arm has to stay in the chain rather than end it, because a rule replacing a chain with
/// a table needs to see that one arm asks a second question and refuse the whole chain.
fn wider_arm(body: &[Stmt]) -> Value {
    arm("wider", String::new(), body, false)
}

fn arm(comparison: &str, literal: String, body: &[Stmt], subject_only: bool) -> Value {
    json!({
        "comparison": comparison,
        "literal": literal,
        "statement_count": body.len(),
        "returns_value": matches!(body.last(), Some(Stmt::Return(held)) if held.value.is_some()),
        "reads_subject_only": subject_only,
    })
}

fn comparison_name(operator: &ruff_python_ast::CmpOp) -> &'static str {
    use ruff_python_ast::CmpOp;
    match operator {
        CmpOp::Eq => "equals",
        CmpOp::NotEq => "differs",
        CmpOp::Is => "identity",
        CmpOp::IsNot => "not_identity",
        CmpOp::In => "membership",
        CmpOp::NotIn => "not_membership", // codespell:ignore
        _ => "ordering",
    }
}

fn literal_text(expression: &Expr) -> String {
    match expression {
        Expr::StringLiteral(item) => item.value.to_str().to_string(),
        Expr::NumberLiteral(item) => format!("{:?}", item.value),
        Expr::BooleanLiteral(item) => item.value.to_string(),
        _ => String::new(),
    }
}

/// Every enumeration one file declares, with the values its members state.
///
/// The two lists this family carries beside the declarations are `scopes` and `files`, and neither
/// is a question one file can answer. Where a reused enum belongs is decided by every module that
/// imports it, and whether a shared `enums` package holds one enum per module is a claim about the
/// package rather than about any file in it. Both need a repository pass the way `ExceptionFact`
/// has one, so this builder states the declarations and leaves the two lists to it.
pub fn enums(module: &ModModule) -> Value {
    let declared: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => enum_analysis(item),
            _ => None,
        })
        .collect();
    json!({"enums": declared, "scopes": [], "files": []})
}

fn enum_analysis(item: &ruff_python_ast::StmtClassDef) -> Option<Value> {
    let bases: Vec<String> = item
        .arguments
        .as_ref()
        .map(|arguments| arguments.args.iter().map(qualified_name).collect())
        .unwrap_or_default();
    let kind = enum_kind(&bases)?;
    let members: Vec<Value> = item
        .body
        .iter()
        .enumerate()
        .filter_map(|(position, member)| enum_member(member, position, kind))
        .collect();
    Some(json!({
        "name": item.name.to_string(),
        "kind": kind,
        "members": members,
        "overrides_generate_next_value": item
            .body
            .iter()
            .any(|member| matches!(member, Stmt::FunctionDef(function)
                if function.name.as_str() == "_generate_next_value_")),
    }))
}

fn enum_kind(bases: &[String]) -> Option<&'static str> {
    bases
        .iter()
        .find_map(|base| match base.rsplit('.').next().unwrap_or(base) {
            "StrEnum" => Some("str_enum"),
            "IntEnum" => Some("int_enum"),
            "IntFlag" => Some("int_flag"),
            "Flag" => Some("flag"),
            "Enum" => Some("enum"),
            _ => None,
        })
}

fn enum_member(member: &Stmt, position: usize, kind: &str) -> Option<Value> {
    let Stmt::Assign(assignment) = member else {
        return None;
    };
    let Expr::Name(target) = assignment.targets.first()? else {
        return None;
    };
    let name = target.id.to_string();
    let automatic = if kind == "str_enum" {
        json!(name.to_lowercase())
    } else {
        json!(position + 1)
    };
    Some(json!({
        "name": name,
        "explicit_value": match assignment.value.as_ref() {
            Expr::StringLiteral(literal) => json!(literal.value.to_str()),
            Expr::NumberLiteral(literal) => json!(format!("{:?}", literal.value)),
            _ => json!(""),
        },
        "standard_auto_value": automatic,
    }))
}

/// Every suppression one file carries, with the metadata it justifies itself by.
///
/// A waiver justifies itself where it is written, in `field=value` pairs after the marker, so
/// `reason=`, `since=`, and `expires=` are read from the line that carries the suppression. A
/// waiver stating no date has an unknown age rather than a young one, which is the reading a rule
/// counting debt already relies on.
pub fn waivers(source: &Source, module: &ModModule) -> Value {
    let suppressions: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| {
            let text = source.slice(statement.range());
            let marker = [
                "# noqa",
                "# type: ignore",
                "# pyrefly: ignore",
                "# ty: ignore",
            ]
            .iter()
            .find(|marker| text.contains(**marker))?;
            let offset = text.find(*marker).unwrap_or_default();
            let tail = text[offset + marker.len()..]
                .split('\n')
                .next()
                .unwrap_or_default();
            let stated = waiver_metadata(tail);
            Some(json!({
                "location": format!(
                    "{}:{}",
                    source.relative,
                    source.line_of(statement.range().start())
                ),
                "is_overly_broad": text.contains(&format!("{marker}\n"))
                    || text.ends_with(*marker),
                "age_days": stated.get("since").and_then(|held| days_since(held)),
                "expires_in_days": stated
                    .get("expires")
                    .and_then(|held| days_since(held).map(|days| -days)),
                "metadata": stated,
            }))
        })
        .collect();
    json!({"waivers": suppressions})
}

/// Return the `field=value` pairs one suppression states, each value running to the next field.
fn waiver_metadata(tail: &str) -> BTreeMap<String, String> {
    let mut found = BTreeMap::new();
    let mut field: Option<String> = None;
    let mut value = String::new();
    for token in tail.split_whitespace() {
        match token.split_once('=') {
            Some((name, first)) if !name.is_empty() && name.chars().all(char::is_alphabetic) => {
                if let Some(held) = field.take() {
                    found.insert(held, value.trim().to_string());
                }
                field = Some(name.to_string());
                value = first.to_string();
            }
            _ => {
                value.push(' ');
                value.push_str(token);
            }
        }
    }
    if let Some(held) = field {
        found.insert(held, value.trim().to_string());
    }
    found
}

/// Return how many days have passed since one written date, which is negative for a future one.
fn days_since(written: &str) -> Option<i64> {
    let stated = civil_days(written)?;
    let today = i64::try_from(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .ok()?
            .as_secs()
            / 86_400,
    )
    .ok()?;
    Some(today - stated)
}

/// Return how many days one `YYYY-MM-DD` date sits after the epoch, by Howard Hinnant's algorithm.
fn civil_days(written: &str) -> Option<i64> {
    let mut parts = written.split('-');
    let year: i64 = parts.next()?.parse().ok()?;
    let month: i64 = parts.next()?.parse().ok()?;
    let day: i64 = parts.next()?.parse().ok()?;
    if !(1..=12).contains(&month) || !(1..=31).contains(&day) || parts.next().is_some() {
        return None;
    }
    let shifted = year - i64::from(month <= 2);
    let era = if shifted >= 0 { shifted } else { shifted - 399 } / 400;
    let year_of_era = shifted - era * 400;
    let day_of_year = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    Some(era * 146_097 + day_of_era - 719_468)
}

/// Every parameter one file annotates, with the operations its body performs on it.
pub fn parameters(source: &Source, module: &ModModule) -> Value {
    let uses: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => Some(item),
            _ => None,
        })
        .flat_map(|item| {
            item.parameters
                .iter()
                .filter_map(|parameter| {
                    let annotation = parameter.annotation()?;
                    let mut read = Uses::default();
                    read.read_body(&item.body, parameter.name());
                    Some(json!({
                        "name": parameter.name().to_string(),
                        "owner": item.name.to_string(),
                        "span": source.span(parameter.range()),
                        "annotation": annotation_name(annotation),
                        "operations": read.operations.iter().collect::<Vec<_>>(),
                        "attribute_reads": read.attributes,
                        "all_uses_known": read.unrecognized == 0,
                        "is_return_value": read.returned,
                    }))
                })
                .collect::<Vec<_>>()
        })
        .collect();
    json!({"parameters": uses})
}

/// Every builtin that reads a value without keeping it, named by the capability it needs.
const READING_BUILTINS: &[&str] = &[
    "len",
    "iter",
    "reversed",
    "sorted",
    "enumerate",
    "sum",
    "min",
    "max",
    "any",
    "all",
    "next",
];

/// What one body does with a name it did not bind, and whether every use of it was recognized.
///
/// A rule reading the operations has to know the list is complete before it concludes anything, so
/// an unrecognized use is counted rather than dropped. Handing the name to a call, aliasing it, or
/// starring it into another signature all leak it somewhere this file stops being able to see, and
/// each one leaves `unrecognized` above zero.
#[derive(Default)]
struct Uses {
    operations: BTreeSet<String>,
    attributes: Vec<String>,
    returned: bool,
    unrecognized: usize,
}

impl Uses {
    fn read_body(&mut self, body: &[Stmt], name: &str) {
        for statement in walk_body(body) {
            let mut held = stated(statement);
            match statement {
                Stmt::Return(item)
                    if item
                        .value
                        .as_deref()
                        .is_some_and(|held| is_named(held, name)) =>
                {
                    self.returned = true;
                }
                Stmt::For(item) if is_named(&item.iter, name) => {
                    self.operations.insert("iter".to_string());
                }
                _ => {}
            }
            held.retain(|expression| !is_named(expression, name));
            for expression in held {
                self.read(expression, name);
            }
        }
    }

    /// Read one expression, naming what it does with the name and walking what is left of it.
    fn read(&mut self, expression: &Expr, name: &str) {
        if is_named(expression, name) {
            self.unrecognized += 1;
            return;
        }
        for child in self.recognize(expression, name) {
            self.read(child, name);
        }
    }

    /// Record the operation one expression performs and return the children still to be read.
    fn recognize<'source>(&mut self, expression: &'source Expr, name: &str) -> Vec<&'source Expr> {
        match expression {
            Expr::Attribute(item) if is_named(&item.value, name) => {
                self.attributes.push(item.attr.to_string());
                Vec::new()
            }
            Expr::Subscript(item) if is_named(&item.value, name) => {
                self.operations.insert("getitem".to_string());
                vec![item.slice.as_ref()]
            }
            Expr::Call(item) => self.recognize_call(item, name),
            Expr::Compare(item)
                if is_membership(&item.ops)
                    && item.comparators.iter().any(|held| is_named(held, name)) =>
            {
                self.operations.insert("contains".to_string());
                vec![item.left.as_ref()]
            }
            Expr::BinOp(item) if is_named(&item.left, name) || is_named(&item.right, name) => {
                self.operations.insert("arithmetic".to_string());
                Vec::new()
            }
            Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
                self.recognize_comprehension(expression, name)
            }
            _ => children(expression),
        }
    }

    fn recognize_call<'source>(
        &mut self,
        item: &'source ruff_python_ast::ExprCall,
        name: &str,
    ) -> Vec<&'source Expr> {
        let mut remaining: Vec<&Expr> = item
            .arguments
            .args
            .iter()
            .chain(item.arguments.keywords.iter().map(|keyword| &keyword.value))
            .collect();
        let called = qualified_name(&item.func);
        if let Expr::Attribute(method) = item.func.as_ref()
            && is_named(&method.value, name)
        {
            self.operations.insert(method.attr.to_string());
        } else if READING_BUILTINS.contains(&called.as_str())
            && item.arguments.args.iter().any(|held| is_named(held, name))
        {
            self.operations.insert(called);
            remaining.retain(|held| !is_named(held, name));
        } else {
            remaining.push(item.func.as_ref());
        }
        remaining
    }

    fn recognize_comprehension<'source>(
        &mut self,
        expression: &'source Expr,
        name: &str,
    ) -> Vec<&'source Expr> {
        let mut remaining: Vec<&Expr> = match expression {
            Expr::ListComp(item) => vec![item.elt.as_ref()],
            Expr::SetComp(item) => vec![item.elt.as_ref()],
            Expr::Generator(item) => vec![item.elt.as_ref()],
            Expr::DictComp(item) => item
                .key
                .iter()
                .map(AsRef::as_ref)
                .chain(std::iter::once(item.value.as_ref()))
                .collect(),
            _ => Vec::new(),
        };
        for generator in comprehension_clauses(expression) {
            if is_named(&generator.iter, name) {
                self.operations.insert("iter".to_string());
            } else {
                remaining.push(&generator.iter);
            }
            remaining.extend(generator.ifs.iter());
        }
        remaining
    }
}

/// Every method one file declares, normalized so identical siblings can be found.
pub fn method_groups(source: &Source, module: &ModModule) -> Value {
    let mut groups: Vec<Value> = Vec::new();
    for statement in walk(module) {
        let Stmt::ClassDef(class) = statement else {
            continue;
        };
        let base = class
            .arguments
            .as_ref()
            .and_then(|arguments| arguments.args.first().map(qualified_name))
            .unwrap_or_default();
        for member in &class.body {
            if let Stmt::FunctionDef(method) = member {
                let body = docstring(&method.body)
                    .map_or_else(|| method.body.as_slice(), |_| &method.body[1..]);
                groups.push(json!({
                    "normalized_definition": normalized(source, method, body),
                    "locations": [format!(
                        "{}:{}",
                        source.relative,
                        source.line_of(member.range().start())
                    )],
                    "direct_base": base.clone(),
                }));
            }
        }
    }
    json!({"groups": groups})
}

fn normalized(
    source: &Source,
    method: &ruff_python_ast::StmtFunctionDef,
    body: &[Stmt],
) -> String {
    let statements: String = body
        .iter()
        .map(|statement| {
            source
                .slice(statement.range())
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
        })
        .collect::<Vec<_>>()
        .join("; ");
    format!(
        "{}({})->{statements}",
        method.name,
        method.parameters.iter().count()
    )
}

/// Every equal string literal one file repeats in one role, and the enum tables beside them.
///
/// Two strings that read the same in two different places are not the same decision, so a group is
/// keyed by the role as well as the value. A keyword name on a call and one side of an equality
/// test are the two roles a project-owned value takes, and everything else is where a repeated
/// string is ordinary vocabulary rather than a policy, which is what the exclusion says out loud.
pub fn literal_groups(source: &Source, module: &ModModule) -> Value {
    let mut counts: BTreeMap<(String, &'static str), usize> = BTreeMap::new();
    for statement in walk(module) {
        for expression in stated(statement) {
            count_literals(expression, "value", &mut counts);
        }
    }
    let groups: Vec<Value> = counts
        .into_iter()
        .filter(|((value, _), count)| *count > 1 && value.len() > 3)
        .map(|((value, role), count)| {
            json!({
                "value": value,
                "role": role,
                "occurrence_count": count,
                "files": [source.relative.clone()],
                "is_excluded_vocabulary": role == "value",
            })
        })
        .collect();
    json!({
        "string_groups": groups,
        "enum_metadata_maps": enum_metadata_maps(module),
    })
}

fn count_literals(
    expression: &Expr,
    role: &'static str,
    counts: &mut BTreeMap<(String, &'static str), usize>,
) {
    if let Expr::StringLiteral(item) = expression {
        *counts
            .entry((item.value.to_str().to_string(), role))
            .or_default() += 1;
    }
    for (child, held) in literal_roles(expression, role) {
        count_literals(child, held, counts);
    }
}

/// Return the children of one expression, each with the role the literals inside it occupy.
fn literal_roles<'source>(
    expression: &'source Expr,
    role: &'static str,
) -> Vec<(&'source Expr, &'static str)> {
    match expression {
        Expr::Call(item) => item
            .arguments
            .args
            .iter()
            .map(|argument| (argument, "value"))
            .chain(
                item.arguments
                    .keywords
                    .iter()
                    .map(|keyword| (&keyword.value, "keyword")),
            )
            .chain(std::iter::once((item.func.as_ref(), "value")))
            .collect(),
        Expr::Compare(item) if matches!(item.ops.as_ref(), [ruff_python_ast::CmpOp::Eq]) => {
            std::iter::once((item.left.as_ref(), "comparison"))
                .chain(item.comparators.iter().map(|held| (held, "comparison")))
                .collect()
        }
        _ => children(expression)
            .into_iter()
            .map(|child| (child, role))
            .collect(),
    }
}

/// Return every literal mapping one file keys entirely by members of one enum it declares.
fn enum_metadata_maps(module: &ModModule) -> Vec<Value> {
    let enums = Enums::of(module);
    let mut found = Vec::new();
    for statement in walk(module) {
        for expression in stated(statement) {
            collect_metadata_maps(expression, &enums, &mut found);
        }
    }
    found
}

fn collect_metadata_maps(expression: &Expr, enums: &Enums, found: &mut Vec<Value>) {
    if let Expr::Dict(item) = expression
        && !item.items.is_empty()
    {
        let members: Vec<(String, String)> = item
            .items
            .iter()
            .filter_map(|entry| enum_member_key(entry.key.as_ref()?, enums))
            .collect();
        let values: Vec<String> = item
            .items
            .iter()
            .filter_map(|entry| match &entry.value {
                Expr::StringLiteral(held) => Some(held.value.to_str().to_string()),
                _ => None,
            })
            .collect();
        let owner = members.first().map(|(held, _)| held.clone());
        found.push(json!({
            "enum_name": owner.clone().unwrap_or_default(),
            "keys": members.iter().map(|(_, held)| held).collect::<Vec<_>>(),
            "values": values.clone(),
            "all_keys_resolve_to_enum": members.len() == item.items.len()
                && values.len() == item.items.len()
                && members.iter().all(|(held, _)| Some(held) == owner.as_ref()),
        }));
    }
    for child in children(expression) {
        collect_metadata_maps(child, enums, found);
    }
}

/// Return the enumeration and member name one mapping key states, when it names one.
fn enum_member_key(key: &Expr, enums: &Enums) -> Option<(String, String)> {
    let Expr::Attribute(item) = key else {
        return None;
    };
    let owner = qualified_name(&item.value);
    enums.holds(&owner).then(|| {
        (
            owner,
            format!("{}.{}", qualified_name(&item.value), item.attr),
        )
    })
}

/// Every test one file declares, with the fixtures, marks, and module state each reaches.
///
/// Whether a runner collects a callable is read from where it sits rather than from its name. A
/// module-level `test` callable is collected, one declared in a `Test` class with no initializer
/// is collected as a method, and one nested inside another callable is never reached at all.
pub fn test_functions(source: &Source, module: &ModModule) -> Value {
    let fixtures = fixture_parameters(module);
    let state = module_state(module);
    let mut tests = Vec::new();
    for (item, collected) in declared_tests(&module.body) {
        let requested: Vec<String> = item
            .parameters
            .iter()
            .map(|parameter| parameter.name().to_string())
            .collect();
        tests.push(json!({
            "name": item.name.to_string(),
            "path": source.relative.clone(),
            "is_collected": collected,
            "is_async": item.is_async,
            "requested_fixture_names": requested.clone(),
            "marks": item
                .decorator_list
                .iter()
                .map(|decorator| qualified_name(&decorator.expression))
                .collect::<Vec<_>>(),
            "calls": test_calls(source, &item.body, item.is_async),
            "owned_conditional_count": conditional_count(&item.body),
            "owned_statement_count": item.body.len(),
            "module_state_mutation_count": module_state_mutations(&item.body, &state),
            "parametrized_range_sizes": parametrized_sizes(item),
            "fixture_names": reached_fixtures(&requested, &fixtures),
        }));
    }
    json!({"tests": tests})
}

/// Return every `test` callable one module states, with whether a runner collects it.
fn declared_tests(body: &[Stmt]) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    let mut found = Vec::new();
    for statement in body {
        match statement {
            Stmt::FunctionDef(item) if item.name.starts_with("test") => {
                found.push((item, true));
                found.extend(nested_tests(&item.body));
            }
            Stmt::ClassDef(item) => {
                let collected = item.name.starts_with("Test") && !states_initializer(item);
                for member in &item.body {
                    match member {
                        Stmt::FunctionDef(method) if method.name.starts_with("test") => {
                            found.push((method, collected));
                            found.extend(nested_tests(&method.body));
                        }
                        _ => {}
                    }
                }
            }
            _ => {
                for block in blocks(statement) {
                    found.extend(nested_tests(block));
                }
            }
        }
    }
    found
}

/// Return every `test` callable declared under one body, none of which a runner reaches.
fn nested_tests(body: &[Stmt]) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    walk_body(body)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) if item.name.starts_with("test") => Some((item, false)),
            _ => None,
        })
        .collect()
}

fn walk_body(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

fn states_initializer(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.body.iter().any(
        |member| matches!(member, Stmt::FunctionDef(method) if method.name.as_str() == "__init__"),
    )
}

/// Return what each fixture one module declares asks for in turn.
fn fixture_parameters(module: &ModModule) -> BTreeMap<String, Vec<String>> {
    walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item)
                if item.decorator_list.iter().any(|decorator| {
                    qualified_name(&decorator.expression).ends_with("fixture")
                }) =>
            {
                Some((
                    item.name.to_string(),
                    item.parameters
                        .iter()
                        .map(|parameter| parameter.name().to_string())
                        .collect(),
                ))
            }
            _ => None,
        })
        .collect()
}

/// Return every fixture one test reaches, following the ones this module declares.
///
/// A test asks for a fixture by name and that fixture asks for others, so the set in play is the
/// closure rather than the signature. Only fixtures this file declares can be followed, since a
/// name a conftest supplies is not stated here.
fn reached_fixtures(
    requested: &[String],
    fixtures: &BTreeMap<String, Vec<String>>,
) -> Vec<String> {
    let mut found: BTreeSet<String> = BTreeSet::new();
    let mut pending: Vec<String> = requested.to_vec();
    while let Some(name) = pending.pop() {
        if !found.insert(name.clone()) {
            continue;
        }
        pending.extend(fixtures.get(&name).into_iter().flatten().cloned());
    }
    found.into_iter().collect()
}

/// Return every module-scope name one file binds, which is the state its tests can share.
fn module_state(module: &ModModule) -> BTreeSet<String> {
    module
        .body
        .iter()
        .flat_map(|statement| match statement {
            Stmt::Assign(item) => item.targets.iter().collect::<Vec<_>>(),
            Stmt::AnnAssign(item) => vec![item.target.as_ref()],
            _ => Vec::new(),
        })
        .filter_map(|target| match target {
            Expr::Name(name) => Some(name.id.to_string()),
            _ => None,
        })
        .collect()
}

/// Return how many times one test writes to state its module holds.
///
/// Rebinding through `global`, mutating a shared collection in place, and writing through a
/// subscript all outlive the test that did them, which is what makes the next test order dependent.
fn module_state_mutations(body: &[Stmt], state: &BTreeSet<String>) -> usize {
    const MUTATING: &[&str] = &[
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "update",
        "add",
        "sort",
        "setdefault",
        "popitem",
        "discard",
    ];
    let mut count = 0;
    for statement in walk_body(body) {
        match statement {
            Stmt::Global(item) => count += item.names.len(),
            Stmt::Assign(item) => {
                count += item
                    .targets
                    .iter()
                    .filter(|target| writes_state(target, state))
                    .count();
            }
            Stmt::AugAssign(item) => count += usize::from(writes_state(&item.target, state)),
            _ => {}
        }
        for expression in stated(statement) {
            count += mutating_calls(expression, state, MUTATING);
        }
    }
    count
}

fn writes_state(target: &Expr, state: &BTreeSet<String>) -> bool {
    match target {
        Expr::Subscript(item) => matches!(item.value.as_ref(), Expr::Name(name)
            if state.contains(name.id.as_str())),
        Expr::Attribute(item) => matches!(item.value.as_ref(), Expr::Name(name)
            if state.contains(name.id.as_str())),
        _ => false,
    }
}

fn mutating_calls(expression: &Expr, state: &BTreeSet<String>, mutating: &[&str]) -> usize {
    let here = match expression {
        Expr::Call(item) => match item.func.as_ref() {
            Expr::Attribute(method) => usize::from(
                mutating.contains(&method.attr.as_str())
                    && matches!(method.value.as_ref(), Expr::Name(name)
                        if state.contains(name.id.as_str())),
            ),
            _ => 0,
        },
        _ => 0,
    };
    here + children(expression)
        .into_iter()
        .map(|child| mutating_calls(child, state, mutating))
        .sum::<usize>()
}

/// Return how many cases each parametrization one test carries states.
fn parametrized_sizes(item: &ruff_python_ast::StmtFunctionDef) -> Vec<usize> {
    item.decorator_list
        .iter()
        .filter(|decorator| qualified_name(&decorator.expression).ends_with("parametrize"))
        .filter_map(|decorator| match &decorator.expression {
            Expr::Call(call) => call.arguments.args.get(1),
            _ => None,
        })
        .filter_map(|cases| match cases {
            Expr::List(item) => Some(item.elts.len()),
            Expr::Tuple(item) => Some(item.elts.len()),
            Expr::Call(item) if qualified_name(&item.func) == "range" => range_size(item),
            _ => None,
        })
        .collect()
}

/// Return how many values one `range` call states, when every bound is written out.
fn range_size(call: &ruff_python_ast::ExprCall) -> Option<usize> {
    let bounds: Vec<i64> = call
        .arguments
        .args
        .iter()
        .filter_map(|argument| match argument {
            Expr::NumberLiteral(item) => match &item.value {
                ruff_python_ast::Number::Int(held) => held.as_i64(),
                _ => None,
            },
            _ => None,
        })
        .collect();
    match bounds.as_slice() {
        [stop] => usize::try_from(*stop).ok(),
        [start, stop] => usize::try_from(stop - start).ok(),
        _ => None,
    }
}

/// Return every call one test body makes, addressed so a rule can point at it.
///
/// Whether a name reaches this repository, the standard library, or a third party is a question
/// about the imports that bound it, which is what `CallFact` answers, so those fields stay unset
/// here rather than being guessed from spelling.
fn test_calls(source: &Source, body: &[Stmt], asynchronous: bool) -> Vec<Value> {
    let mut found = Vec::new();
    for statement in walk_body(body) {
        let assigned = match statement {
            Stmt::Assign(item) => item.targets.first().map(bound_name).unwrap_or_default(),
            _ => String::new(),
        };
        let discarded = matches!(statement, Stmt::Expr(_));
        for expression in stated(statement) {
            let outermost = matches!(expression, Expr::Call(_));
            collect_test_calls(
                source,
                expression,
                &Placement {
                    assigned: &assigned,
                    discarded: discarded && outermost,
                    asynchronous,
                },
                &mut found,
            );
        }
    }
    found
}

/// Where one call sits, which is what tells a discarded result from a bound one.
struct Placement<'source> {
    assigned: &'source str,
    discarded: bool,
    asynchronous: bool,
}

fn collect_test_calls(
    source: &Source,
    expression: &Expr,
    placement: &Placement,
    found: &mut Vec<Value>,
) {
    if let Expr::Call(item) = expression {
        let called = qualified_name(&item.func);
        let last = called.rsplit('.').next().unwrap_or(&called).to_string();
        found.push(json!({
            "qualified_name": called,
            "path": source.relative.clone(),
            "arguments": item
                .arguments
                .args
                .iter()
                .map(|argument| expression_value(source, argument))
                .collect::<Vec<_>>(),
            "keyword_names": item
                .arguments
                .keywords
                .iter()
                .filter_map(|keyword| keyword.arg.as_ref().map(ToString::to_string))
                .collect::<Vec<_>>(),
            "receiver": match item.func.as_ref() {
                Expr::Attribute(held) => Some(expression_value(source, &held.value)),
                _ => None,
            },
            "assigned_target": placement.assigned,
            "result_is_discarded": placement.discarded,
            "is_constructor": last.chars().next().is_some_and(char::is_uppercase),
            "has_starred_arguments": item
                .arguments
                .args
                .iter()
                .any(|argument| matches!(argument, Expr::Starred(_))),
            "enclosing_is_async": placement.asynchronous,
            "node": source.node_of("call", item),
        }));
    }
    for child in children(expression) {
        collect_test_calls(source, child, placement, found);
    }
}

/// Return one expression written down the way a rule reading a call argument needs it.
fn expression_value(source: &Source, expression: &Expr) -> Value {
    json!({
        "text": source.slice(expression.range()),
        "qualified_name": qualified_name(expression),
        "literal_kind": literal_kind(expression).unwrap_or("none"),
        "node": source.node_of("expression", expression),
    })
}

fn conditional_count(body: &[Stmt]) -> usize {
    let mut pending: Vec<&Stmt> = body.iter().collect();
    let mut count = 0;
    while let Some(statement) = pending.pop() {
        if matches!(statement, Stmt::If(_)) {
            count += 1;
        }
        for block in blocks(statement) {
            pending.extend(block.iter());
        }
    }
    count
}

/// Every sibling test whose syntax matches once its literals are removed.
///
/// The literals have to leave the syntax for two tests to be siblings at all, since the whole
/// question is whether they differ in nothing but their data. What each one stated travels beside
/// the shape as its own vector, so a rule can see whether the vectors repeat.
pub fn test_case_groups(source: &Source, module: &ModModule) -> Value {
    let mut shapes: BTreeMap<String, Vec<Vec<String>>> = BTreeMap::new();
    for statement in walk(module) {
        if let Stmt::FunctionDef(item) = statement
            && item.name.starts_with("test")
        {
            let (shape, vector) = literal_shape(source, &item.body);
            shapes.entry(shape).or_default().push(vector);
        }
    }
    let groups: Vec<Value> = shapes
        .into_iter()
        .map(|(syntax, vectors)| {
            json!({
                "normalized_syntax": syntax,
                "literal_vectors": vectors,
            })
        })
        .collect();
    json!({"groups": groups, "loops": literal_loops(module)})
}

/// Return one body written with every literal replaced, beside the literals it stated in order.
fn literal_shape(source: &Source, body: &[Stmt]) -> (String, Vec<String>) {
    let mut ranges = Vec::new();
    for statement in walk_body(body) {
        for expression in stated(statement) {
            collect_literal_ranges(expression, &mut ranges);
        }
    }
    ranges.sort_by_key(|range: &ruff_text_size::TextRange| range.start());
    let whole = body_range(body);
    let mut shape = String::new();
    let mut vector = Vec::new();
    let mut cursor = whole.start();
    for range in ranges {
        if range.start() < cursor {
            continue;
        }
        shape.push_str(source.slice(ruff_text_size::TextRange::new(cursor, range.start())));
        shape.push('?');
        vector.push(source.slice(range).to_string());
        cursor = range.end();
    }
    shape.push_str(source.slice(ruff_text_size::TextRange::new(cursor, whole.end())));
    (
        shape.split_whitespace().collect::<Vec<_>>().join(" "),
        vector,
    )
}

fn collect_literal_ranges(expression: &Expr, ranges: &mut Vec<ruff_text_size::TextRange>) {
    if matches!(
        expression,
        Expr::StringLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
    ) {
        ranges.push(expression.range());
    }
    for child in children(expression) {
        collect_literal_ranges(child, ranges);
    }
}

/// Return every loop a test owns that walks a table of cases the source writes out.
fn literal_loops(module: &ModModule) -> Vec<Value> {
    let mut found = Vec::new();
    for (item, _) in declared_tests(&module.body) {
        for statement in walk_body(&item.body) {
            let Stmt::For(loop_statement) = statement else {
                continue;
            };
            let cases = match loop_statement.iter.as_ref() {
                Expr::List(held) => held.elts.len(),
                Expr::Tuple(held) => held.elts.len(),
                _ => continue,
            };
            found.push(json!({
                "case_count": cases,
                "owns_assertion": walk_body(&loop_statement.body)
                    .iter()
                    .any(|held| matches!(held, Stmt::Assert(_))),
            }));
        }
    }
    found
}

/// Every model one file declares that a validator or a constructor shapes.
pub fn pydantic_models(module: &ModModule) -> Value {
    let models: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => Some(item),
            _ => None,
        })
        .filter(|item| is_model(item) || is_plain_class(item))
        .map(|item| {
            let validators: Vec<Value> = item
                .body
                .iter()
                .filter_map(|member| match member {
                    Stmt::FunctionDef(method) => validator(method),
                    _ => None,
                })
                .collect();
            let initializers: Vec<&ruff_python_ast::StmtFunctionDef> = item
                .body
                .iter()
                .filter_map(|member| match member {
                    Stmt::FunctionDef(method) if method.name.as_str() == "__init__" => {
                        Some(method)
                    }
                    _ => None,
                })
                .collect();
            let constructed = initializers.first();
            json!({
                "name": item.name.to_string(),
                "validators": validators,
                "is_undecorated_plain_class": is_plain_class(item),
                "synchronous_init_count": initializers
                    .iter()
                    .filter(|method| !method.is_async)
                    .count(),
                "fixed_parameter_count": constructed
                    .map(|method| method.parameters.iter().count().saturating_sub(1))
                    .unwrap_or_default(),
                "stored_parameter_count": constructed
                    .map(|method| stored_parameters(method))
                    .unwrap_or_default(),
                "validation_count": constructed
                    .map(|method| {
                        walk_body(&method.body)
                            .iter()
                            .filter(|held| matches!(held, Stmt::Raise(_) | Stmt::Assert(_)))
                            .count()
                    })
                    .unwrap_or_default(),
                "default_count": constructed
                    .map(|method| {
                        method
                            .parameters
                            .iter()
                            .filter(|parameter| parameter.default().is_some())
                            .count()
                    })
                    .unwrap_or_default(),
                "has_only_data_identity_methods": states_only_data_identity(item),
            })
        })
        .collect();
    json!({"models": models})
}

/// Whether one class derives from something naming itself a model.
fn is_model(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.arguments.as_ref().is_some_and(|arguments| {
        arguments
            .args
            .iter()
            .any(|base| qualified_name(base).contains("Model"))
    })
}

/// Whether one class is an ordinary class nothing has already turned into a data holder.
///
/// A base or a decorator is somebody else already answering the question, so a candidate for
/// becoming a model is a class that derives nothing and carries no decorator at all.
fn is_plain_class(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.decorator_list.is_empty()
        && item
            .arguments
            .as_ref()
            .is_none_or(|arguments| arguments.args.is_empty() && arguments.keywords.is_empty())
}

/// Return how many of one initializer's parameters it stores on the receiver unchanged.
fn stored_parameters(method: &ruff_python_ast::StmtFunctionDef) -> usize {
    let names: BTreeSet<&str> = method
        .parameters
        .iter()
        .map(|parameter| parameter.name().as_str())
        .collect();
    let mut stored = BTreeSet::new();
    for statement in walk_body(&method.body) {
        let Stmt::Assign(item) = statement else {
            continue;
        };
        let Expr::Name(value) = item.value.as_ref() else {
            continue;
        };
        let assigns_receiver = item.targets.iter().any(|target| {
            matches!(target, Expr::Attribute(held)
                if matches!(held.value.as_ref(), Expr::Name(receiver) if receiver.id == "self"))
        });
        if assigns_receiver && names.contains(value.id.as_str()) {
            stored.insert(value.id.as_str());
        }
    }
    stored.len()
}

/// Whether every method one class states beside its initializer is a data identity protocol.
fn states_only_data_identity(item: &ruff_python_ast::StmtClassDef) -> bool {
    const IDENTITY: &[&str] = &[
        "__init__",
        "__eq__",
        "__ne__",
        "__hash__",
        "__repr__",
        "__str__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__post_init__",
    ];
    item.body.iter().all(|member| match member {
        Stmt::FunctionDef(method) => IDENTITY.contains(&method.name.as_str()),
        _ => true,
    })
}

fn validator(method: &ruff_python_ast::StmtFunctionDef) -> Option<Value> {
    let decorators: Vec<String> = method
        .decorator_list
        .iter()
        .map(|decorator| qualified_name(&decorator.expression))
        .collect();
    let kind = decorators.iter().find_map(|decorator| {
        match decorator.rsplit('.').next().unwrap_or(decorator) {
            "field_validator" => Some("field"),
            "model_validator" => Some("model_after"),
            _ => None,
        }
    })?;
    Some(json!({
        "kind": kind,
        "fields_read": [],
        "has_self_call": false,
        "has_nonfield_access": false,
        "declarative_constraint_count": 0,
        "proves_disjoint_optional_variants": false,
        "variant_count": 0,
    }))
}

/// Every database operation chain one file writes through SQLAlchemy or SQLModel.
pub fn queries(source: &Source, module: &ModModule) -> Value {
    let mut operations = Vec::new();
    for statement in walk(module) {
        let inside_loop = matches!(statement, Stmt::For(_) | Stmt::While(_));
        for expression in expressions(statement) {
            collect_queries(source, expression, inside_loop, &mut operations);
        }
        for block in blocks(statement) {
            for nested in block {
                for expression in expressions(nested) {
                    collect_queries(source, expression, inside_loop, &mut operations);
                }
            }
        }
    }
    json!({"operations": operations})
}

fn collect_queries(source: &Source, expression: &Expr, inside_loop: bool, found: &mut Vec<Value>) {
    if let Expr::Call(item) = expression {
        let name = qualified_name(&item.func);
        if let Some(kind) = query_kind(&name) {
            // A session factory states its own settling policy, and the keywords it carries are
            // the whole of the evidence for it. One this reader does not know changes what the
            // factory does, so it is recorded rather than assumed away.
            const KNOWN: &[&str] = &[
                "bind",
                "class_",
                "expire_on_commit",
                "autoflush",
                "autobegin",
                "info",
                "join_transaction_mode",
            ];
            let keywords = &item.arguments.keywords;
            found.push(json!({
                "kind": kind,
                "framework": if name.contains("exec") { "sqlmodel" } else { "sqlalchemy" },
                "is_inside_loop": inside_loop,
                "expire_on_commit": keywords
                    .iter()
                    .find(|keyword| {
                        keyword.arg.as_ref().is_some_and(|named| named == "expire_on_commit")
                    })
                    .is_none_or(|keyword| !matches!(&keyword.value, Expr::BooleanLiteral(held)
                        if !held.value)),
                "has_unknown_keywords": keywords.iter().any(|keyword| {
                    keyword
                        .arg
                        .as_ref()
                        .is_none_or(|named| !KNOWN.contains(&named.as_str()))
                }),
                "selected_expression_count": item.arguments.args.len(),
                "has_primary_key_equality": false,
                "has_execution_options": false,
                "node": source.node_of("call", item),
            }));
        }
    }
    for child in children(expression) {
        collect_queries(source, child, inside_loop, found);
    }
}

fn query_kind(name: &str) -> Option<&'static str> {
    let tail = name.rsplit('.').next().unwrap_or(name);
    match tail {
        "async_sessionmaker" => Some("async_sessionmaker"),
        "commit" => Some("session_commit"),
        "scalars" => Some("execute_scalars"),
        _ => None,
    }
}

/// Everything one file states about itself as prose, from its own docstrings.
///
/// A paragraph is what a blank line separates, which is the same split a reader performs, and the
/// opener is only asked of a callable because a class states what it is rather than what it does.
pub fn prose(module: &ModModule) -> Value {
    let documented: Vec<(bool, String)> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => docstring(&item.body).map(|text| (true, text)),
            Stmt::ClassDef(item) => docstring(&item.body).map(|text| (false, text)),
            _ => None,
        })
        .collect();
    let counted = |text: &str, split: &dyn Fn(&str) -> Vec<String>| -> Vec<usize> {
        split(text)
            .iter()
            .map(|part| part.split_whitespace().count())
            .filter(|count| *count > 0)
            .collect()
    };
    let sentences: Vec<usize> = documented
        .iter()
        .flat_map(|(_, text)| {
            counted(text, &|held| {
                held.split(['.', '!', '?']).map(str::to_string).collect()
            })
        })
        .collect();
    let paragraphs: Vec<usize> = documented
        .iter()
        .flat_map(|(_, text)| {
            counted(text, &|held| {
                held.split("\n\n").map(str::to_string).collect()
            })
        })
        .collect();
    let openers: Vec<String> = documented
        .iter()
        .filter(|(callable, _)| *callable)
        .filter_map(|(_, text)| text.split_whitespace().next().map(str::to_lowercase))
        .collect();
    json!({
        "sections": [{
            "sentence_word_counts": sentences,
            "paragraph_word_counts": paragraphs,
            "sentence_openers": openers,
        }]
    })
}
