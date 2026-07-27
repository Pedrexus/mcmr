use crate::comments;
use crate::discovery::Document;
use crate::graph::{
    Edge, EdgeKind, Language, Node, NodeKind, ParameterKind, Reference, Resolution, Stated,
    Visibility, attach, identity, node, parameter, stray,
};
use crate::protocol::Stats;
use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use syn::spanned::Spanned;
use syn::visit::Visit;
use syn::{FnArg, ImplItem, Item, ReturnType, Signature, TraitItem, Type, UseTree};

/// Build every requested fact family from one Rust document.
///
/// The families are the ones every frontend fills, because a general rule reads the same fact
/// whichever language produced it. Rust spells the shared ideas its own way: `pub` is the
/// visibility keyword, an `impl` block holds the methods of the type it names, a trait is the
/// contract a type implements, and `use` is the import.
pub fn extract(document: &Document, facts: &mut BTreeMap<String, Vec<Value>>, stats: &mut Stats) {
    let Ok(parsed) = syn::parse_file(&document.source) else {
        stats.parse_failure_count += 1;
        return;
    };
    let source = Source::new(&document.relative, &document.source);
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_fact(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(function_facts(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("RustSurfaceFact") {
        stream.push(surface_fact(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("CallFact") {
        stream.push(call_fact(&source, &parsed));
    }
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comments::fact(
            &source,
            "rust",
            scan(&source.text),
            &mut Notes,
        ));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(syntax_facts(&source, &parsed));
    }
}

/// What Rust says about its own comments, past what the shared reader already settles.
struct Notes;

impl comments::Dialect for Notes {
    /// Whether one comment addresses a tool rather than a reader.
    ///
    /// Rust states most of its suppressions as attributes, which are code and never reach here.
    /// What is left is the switches the tools around the compiler still read from a comment, and
    /// all of them are written as the opening word.
    fn is_directive(&mut self, body: &str) -> bool {
        comments::opens_with(
            body,
            &[
                "rustfmt",
                "clippy",
                "tarpaulin",
                "grcov",
                "coverage:",
                "codecov",
                "cspell",
                "cbindgen",
            ],
        )
    }

    /// Whether one comment body is Rust rather than prose, decided by parsing it.
    ///
    /// A block is tried first and a file second, because a commented-out statement is far and away
    /// the common case and settling it takes one parse. A declaration needs the second, since a
    /// block holding one parses as the item rather than as what a body would run.
    ///
    /// A block here yields its last expression, so a note that only calls something is code even
    /// with no semicolon in it, and the punctuation worth handing to the parser is wider than what
    /// a brace language would ask for.
    fn is_source(&mut self, body: &str) -> bool {
        comments::holds_code(body, &['=', '(', ';', '{'])
            && (syn::parse_str::<syn::Block>(&format!("{{{body}}}")).is_ok()
                || syn::parse_file(body).is_ok())
    }
}

/// Return every comment one Rust source states, in the order it states them.
///
/// `syn` keeps a doc comment as an attribute and drops every other one, and the token stream drops
/// them all, so the only reader that sees an ordinary comment is a lexical one. What it has to get
/// right is where a comment is not a comment, since `//` inside a URL and `/*` inside a pattern
/// are text. Strings, raw strings, and characters are therefore stepped over rather than read, and
/// a block comment nests, which is the one place this language differs from its neighbours.
///
/// The cursor walks characters rather than bytes. A source is a `str` and slicing one anywhere but
/// a character boundary panics, so a scanner stepping a byte at a time takes the whole run down
/// the first time an identifier, a literal, or a comment is written in any language but English.
fn scan(text: &str) -> Vec<ruff_text_size::TextRange> {
    let mut found = Vec::new();
    let mut at = 0;
    while let Some(held) = text[at..].chars().next() {
        let rest = &text[at..];
        if rest.starts_with("//") {
            let end = rest.find('\n').map_or(text.len(), |offset| at + offset);
            found.push(comments::at(at, end));
            at = end;
        } else if rest.starts_with("/*") {
            let end = block_end(text, at);
            found.push(comments::at(at, end));
            at = end;
        } else {
            at = match held {
                '"' => quoted_end(text, at + 1, '"'),
                '\'' => character_end(text, at + 1),
                'r' if rest.starts_with("r\"") || rest.starts_with("r#") => raw_end(text, at),
                _ => at + held.len_utf8(),
            };
        }
    }
    found
}

/// Return the offset one character past the one this offset opens.
fn after(text: &str, at: usize) -> usize {
    at + text[at..].chars().next().map_or(0, char::len_utf8)
}

/// Return where one nested block comment closes, which is where its last `*/` matches its first.
fn block_end(text: &str, at: usize) -> usize {
    let mut depth = 0;
    let mut cursor = at;
    while cursor < text.len() {
        let rest = &text[cursor..];
        if rest.starts_with("/*") {
            depth += 1;
            cursor += 2;
        } else if rest.starts_with("*/") {
            depth -= 1;
            cursor += 2;
            if depth == 0 {
                return cursor;
            }
        } else {
            cursor = after(text, cursor);
        }
    }
    text.len()
}

/// Return where one quoted literal closes, stepping over whatever a backslash escaped.
fn quoted_end(text: &str, at: usize, closing: char) -> usize {
    let mut cursor = at;
    while let Some(held) = text[cursor..].chars().next() {
        match held {
            '\\' => cursor = after(text, cursor + 1),
            found if found == closing => return cursor + closing.len_utf8(),
            _ => cursor += held.len_utf8(),
        }
    }
    text.len()
}

/// Return where one character literal closes, which a lifetime never does.
///
/// `'a` opens no literal, so a lifetime and a label have to be stepped past or every borrow in the
/// file would swallow the source after it. What tells the two apart is what follows the quote: an
/// escape always opens a literal, and a single character followed by the closing quote does too,
/// whatever that character costs in bytes.
fn character_end(text: &str, at: usize) -> usize {
    let mut held = text[at..].chars();
    match held.next() {
        Some('\\') => quoted_end(text, at, '\''),
        Some(_) if held.next() == Some('\'') => quoted_end(text, at, '\''),
        _ => at,
    }
}

/// Return where one raw string closes, which is the hash count its opening declared.
fn raw_end(text: &str, at: usize) -> usize {
    let hashes = text[at + 1..]
        .chars()
        .take_while(|held| *held == '#')
        .count();
    let opened = at + 1 + hashes;
    let closing = format!("\"{}", "#".repeat(hashes));
    match text[opened..].starts_with('"') {
        true => text[opened + 1..]
            .find(&closing)
            .map_or(text.len(), |offset| opened + 1 + offset + closing.len()),
        false => at + 1,
    }
}

/// Every call this module states, with the ones whose result nobody takes marked as such.
fn call_fact(source: &Source, file: &syn::File) -> Value {
    let mut found = Calls {
        path: source.relative.clone(),
        ..Calls::default()
    };
    found.visit_file(file);
    merge(
        base(
            source,
            &format!("calls:{}", source.relative),
            Span::call_site(),
        ),
        json!({
            "calls": found.calls,
            "module_bindings": file.items.iter().filter_map(declared_name).collect::<Vec<_>>(),
        }),
    )
}

/// Every call one module makes, collected as the visitor meets them.
///
/// A call in statement position ending in a semicolon is the one shape where the language throws
/// the result away, so that is what marks a discarded result. Everything else hands its value to
/// something, even when that something ignores it later, which is a question about the receiver.
#[derive(Default)]
struct Calls {
    path: String,
    calls: Vec<Value>,
    discarded: BTreeSet<(usize, usize)>,
}

impl Calls {
    fn record(&mut self, named: String, at: Span) {
        let opened = at.start();
        self.calls.push(json!({
            "qualified_name": named,
            "path": self.path,
            "result_is_discarded": self.discarded.contains(&(opened.line, opened.column)),
        }));
    }
}

impl Visit<'_> for Calls {
    fn visit_stmt(&mut self, statement: &syn::Stmt) {
        if let syn::Stmt::Expr(held, Some(_)) = statement
            && matches!(held, syn::Expr::Call(_) | syn::Expr::MethodCall(_))
        {
            let opened = held.span().start();
            self.discarded.insert((opened.line, opened.column));
        }
        syn::visit::visit_stmt(self, statement);
    }

    fn visit_expr_call(&mut self, held: &syn::ExprCall) {
        self.record(expression_name(&held.func), held.span());
        syn::visit::visit_expr_call(self, held);
    }

    fn visit_expr_method_call(&mut self, held: &syn::ExprMethodCall) {
        self.record(held.method.to_string(), held.span());
        syn::visit::visit_expr_method_call(self, held);
    }
}

/// Every declaration this file states, each with its source and its tree.
///
/// The kinds are the shared vocabulary rather than Rust's own, so a rule written against a Python
/// declaration reads a Rust one without learning what an `ItemFn` is.
fn syntax_facts(source: &Source, file: &syn::File) -> Vec<Value> {
    let mut facts = Vec::new();
    for item in &file.items {
        match item {
            Item::Fn(declared) => {
                let name = declared.sig.ident.to_string();
                facts.push(declaration(
                    source,
                    &name,
                    "callable",
                    declared.span(),
                    |depth| block_children(source, &declared.block, depth),
                ));
            }
            Item::Impl(block) => {
                let owner = rendered(&block.self_ty);
                for member in &block.items {
                    let ImplItem::Fn(method) = member else {
                        continue;
                    };
                    let name = format!("{owner}::{}", method.sig.ident);
                    facts.push(declaration(
                        source,
                        &name,
                        "callable",
                        method.span(),
                        |depth| block_children(source, &method.block, depth),
                    ));
                }
            }
            _ => {
                let Some(name) = declared_name(item) else {
                    continue;
                };
                if !is_type(item) {
                    continue;
                }
                facts.push(declaration(source, &name, "type", item.span(), |_| {
                    Vec::new()
                }));
            }
        }
    }
    facts
}

fn declaration(
    source: &Source,
    qualname: &str,
    kind: &str,
    at: Span,
    children: impl Fn(usize) -> Vec<Value>,
) -> Value {
    let tree = json!({
        "kind": crate::syntax::known(kind),
        "name": qualname.rsplit("::").next().unwrap_or(qualname),
        "text": spanned(source, at),
        "span": locate(source, at),
        "children": children(SYNTAX_DEPTH),
    });
    crate::syntax::fact(source, "rust", qualname, tree, locate(source, at))
}

/// How far down a declaration's tree a syntax fact reaches, matching the Python frontend.
const SYNTAX_DEPTH: usize = 6;

/// Return the source one span covers, which proc-macro2 gives as a line and column pair.
fn spanned(source: &Source, at: Span) -> String {
    let (start, end) = (at.start(), at.end());
    let lines: Vec<&str> = source.text.lines().collect();
    let picked = lines
        .get(start.line.saturating_sub(1)..end.line.min(lines.len()))
        .unwrap_or_default();
    picked.join("\n")
}

fn block_children(source: &Source, block: &syn::Block, depth: usize) -> Vec<Value> {
    if depth == 0 {
        return Vec::new();
    }
    let last = block.stmts.len().saturating_sub(1);
    block
        .stmts
        .iter()
        .enumerate()
        .map(|(at, statement)| statement_tree(source, statement, depth - 1, at == last))
        .collect()
}

fn statement_tree(source: &Source, statement: &syn::Stmt, depth: usize, is_tail: bool) -> Value {
    let (kind, name) = match statement {
        syn::Stmt::Local(held) => (
            "binding",
            match &held.pat {
                syn::Pat::Ident(ident) => ident.ident.to_string(),
                syn::Pat::Type(typed) => match typed.pat.as_ref() {
                    syn::Pat::Ident(ident) => ident.ident.to_string(),
                    _ => String::new(),
                },
                _ => String::new(),
            },
        ),
        syn::Stmt::Item(_) => ("statement", String::new()),
        syn::Stmt::Macro(_) => ("effect", String::new()),
        // A statement holding an expression is an effect. Only the last statement of a block is
        // that block's value, so only there does a missing semicolon mean a return. A branch or a
        // loop written mid-block carries no semicolon either, and calling one a return would hide
        // every branch and loop from the rules that look for them.
        syn::Stmt::Expr(held, semicolon) => match (semicolon, is_tail) {
            (Some(_), _) => ("effect", expression_name(held)),
            (None, true) => ("return", expression_name(held)),
            (None, false) => (expression_kind(held), expression_name(held)),
        },
    };
    // A statement whose whole content is one expression holds that expression rather than its
    // operands, and is located at the expression rather than at the semicolon that ends it. Both
    // halves are what lets a rule ask what the line computed: `ALL-CONT0002` finds a statement that
    // only produced a value by matching the child covering the whole statement, and an operand or a
    // trailing piece of punctuation each break that match on their own.
    let effect = matches!(statement, syn::Stmt::Expr(_, Some(_)));
    let at = match statement {
        syn::Stmt::Expr(held, Some(_)) => held.span(),
        _ => statement.span(),
    };
    let children = match (depth, statement) {
        (0, _) => Vec::new(),
        (_, syn::Stmt::Local(held)) => held
            .init
            .iter()
            .map(|init| expression_tree(source, &init.expr, depth - 1))
            .collect(),
        (_, syn::Stmt::Expr(held, _)) if effect => vec![expression_tree(source, held, depth - 1)],
        (_, syn::Stmt::Expr(held, _)) => expression_children(source, held, depth - 1),
        _ => Vec::new(),
    };
    json!({
        "kind": crate::syntax::known(kind),
        "name": name,
        "text": spanned(source, at),
        "span": locate(source, at),
        "children": children,
    })
}

fn expression_kind(expression: &syn::Expr) -> &'static str {
    match expression {
        syn::Expr::Call(_) | syn::Expr::MethodCall(_) => "call",
        syn::Expr::Path(_) => "name",
        syn::Expr::Field(_) => "member",
        syn::Expr::Lit(syn::ExprLit {
            lit: syn::Lit::Str(_) | syn::Lit::ByteStr(_),
            ..
        }) => "text",
        syn::Expr::Lit(_) => "literal",
        syn::Expr::Array(_) | syn::Expr::Tuple(_) | syn::Expr::Struct(_) => "collection",
        syn::Expr::If(_) | syn::Expr::Match(_) => "branch",
        syn::Expr::ForLoop(_) | syn::Expr::While(_) | syn::Expr::Loop(_) => "loop",
        syn::Expr::Return(_) => "return",
        syn::Expr::Binary(_) | syn::Expr::Unary(_) => "operation",
        syn::Expr::Index(_) => "index",
        syn::Expr::Await(_) => "await",
        syn::Expr::Closure(_) => "callable",
        syn::Expr::Block(_) | syn::Expr::Unsafe(_) => "scope",
        _ => "expression",
    }
}

/// Return the name one expression states, which for a call is the whole path it reaches through.
///
/// A method call names its receiver as much as its method, and the reference frontend keeps both.
/// Dropping the receiver leaves `state.exec` reading as the bare `exec` that several languages
/// spell a scope builtin with, so every general rule matching a builtin by name answers yes for
/// any value holding a method of that name. A receiver no lexical reader can name leaves the call
/// unnamed rather than named after its method alone, which is the same answer Python gives.
fn expression_name(expression: &syn::Expr) -> String {
    match expression {
        syn::Expr::Path(path) => path_name(&path.path),
        syn::Expr::MethodCall(call) => {
            let reached = expression_name(&call.receiver);
            match reached.is_empty() {
                true => String::new(),
                false => format!("{reached}.{}", call.method),
            }
        }
        syn::Expr::Call(call) => expression_name(&call.func),
        syn::Expr::Field(field) => match &field.member {
            syn::Member::Named(name) => name.to_string(),
            syn::Member::Unnamed(index) => index.index.to_string(),
        },
        _ => String::new(),
    }
}

fn expression_tree(source: &Source, expression: &syn::Expr, depth: usize) -> Value {
    json!({
        "kind": crate::syntax::known(expression_kind(expression)),
        "name": expression_name(expression),
        "text": spanned(source, expression.span()),
        "span": locate(source, expression.span()),
        "children": match depth {
            0 => Vec::new(),
            _ => expression_children(source, expression, depth - 1),
        },
    })
}

/// Return the expressions one expression holds, which is what a tree walks into.
fn expression_children(source: &Source, expression: &syn::Expr, depth: usize) -> Vec<Value> {
    let held: Vec<&syn::Expr> = match expression {
        syn::Expr::Call(call) => call.args.iter().collect(),
        syn::Expr::MethodCall(call) => std::iter::once(call.receiver.as_ref())
            .chain(call.args.iter())
            .collect(),
        syn::Expr::Binary(item) => vec![item.left.as_ref(), item.right.as_ref()],
        syn::Expr::Unary(item) => vec![item.expr.as_ref()],
        syn::Expr::Field(item) => vec![item.base.as_ref()],
        syn::Expr::Index(item) => vec![item.expr.as_ref(), item.index.as_ref()],
        syn::Expr::Await(item) => vec![item.base.as_ref()],
        syn::Expr::Return(item) => item.expr.as_deref().into_iter().collect(),
        syn::Expr::Reference(item) => vec![item.expr.as_ref()],
        syn::Expr::Paren(item) => vec![item.expr.as_ref()],
        syn::Expr::Array(item) => item.elems.iter().collect(),
        syn::Expr::Tuple(item) => item.elems.iter().collect(),
        // A body-opening expression holds statements rather than expressions, and stopping here
        // is what left a Rust tree blind past the first branch or loop it met.
        syn::Expr::Block(item) => return block_children(source, &item.block, depth + 1),
        syn::Expr::Unsafe(item) => return block_children(source, &item.block, depth + 1),
        syn::Expr::Loop(item) => return block_children(source, &item.body, depth + 1),
        syn::Expr::While(item) => return block_children(source, &item.body, depth + 1),
        syn::Expr::ForLoop(item) => return block_children(source, &item.body, depth + 1),
        syn::Expr::If(item) => {
            let mut found = block_children(source, &item.then_branch, depth + 1);
            found.extend(
                item.else_branch
                    .iter()
                    .map(|(_, held)| expression_tree(source, held, depth)),
            );
            return found;
        }
        syn::Expr::Match(item) => {
            return item
                .arms
                .iter()
                .map(|arm| expression_tree(source, &arm.body, depth))
                .collect();
        }
        _ => Vec::new(),
    };
    held.into_iter()
        .map(|child| expression_tree(source, child, depth))
        .collect()
}

/// What one module borrows, what it pins for the whole program, and what it copies instead.
///
/// These three belong in one fact because they are one decision seen from three sides. A lifetime
/// is what borrowing costs in the signature, a clone is what not borrowing costs at run time, and
/// a `'static` is what pinning costs forever. A rule that saw only one of them would push a
/// project straight into the other.
fn surface_fact(source: &Source, file: &syn::File) -> Value {
    let mut surface = Surface::default();
    surface.visit_file(file);
    merge(
        base(
            source,
            &format!("surface:{}", source.relative),
            Span::call_site(),
        ),
        json!({
            "annotations": surface.annotations,
            "pins": surface.pins,
            "clones": surface.clones,
        }),
    )
}

/// Every borrow, pin, and copy one module states, as it is walked.
#[derive(Default)]
struct Surface {
    owners: Vec<String>,
    loop_depth: usize,
    demanding: bool,
    annotations: Vec<Value>,
    pins: Vec<Value>,
    clones: Vec<Value>,
}

impl Surface {
    fn owner(&self) -> String {
        self.owners.last().cloned().unwrap_or_default()
    }

    /// Record the lifetimes one declaration names and every position each of them appears in.
    ///
    /// Where a lifetime appears is what decides whether elision would have produced it, and where
    /// is something only a parser can see. What that arrangement means is a judgment, so it is
    /// left to the rule and only the arrangement is stated here.
    fn annotate(&mut self, generics: &syn::Generics, kind: &str, at: &syn::Ident, at_use: Placed) {
        let names: Vec<String> = generics
            .lifetimes()
            .map(|held| held.lifetime.ident.to_string())
            .collect();
        if names.is_empty() {
            return;
        }
        self.annotations.push(json!({
            "owner": format!("{}{}", self.owner(), at),
            "kind": kind,
            "names": names,
            "line": at.span().start().line,
            "returned": at_use.returned,
            "receiver": at_use.receiver,
            "parameters": at_use.parameters,
            "beyond": at_use.beyond,
        }));
    }
}

/// Every position one signature names a lifetime in, which is what elision turns on.
///
/// Each list holds one entry per position rather than one per distinct name, because elision hands
/// every input position its own fresh lifetime and a name written in two of them is therefore a
/// constraint elision cannot state. Dropping the repeat would hide exactly that case.
#[derive(Default)]
struct Placed {
    returned: Vec<String>,
    receiver: String,
    parameters: Vec<String>,
    beyond: Vec<String>,
}

/// Read where one signature names each of its lifetimes.
///
/// The four places are the ones the elision rules distinguish: what the return states, what the
/// receiver carries, what the other parameters name, and what the bounds, the where clause, or the
/// body still need. A rule reading these four decides whether the annotation says anything the
/// compiler would not have said on its own.
fn placed(signature: &Signature, body: &syn::Block) -> Placed {
    let mut returns = Beyond::default();
    returns.visit_return_type(&signature.output);
    let mut beyond = Beyond::default();
    for parameter in &signature.generics.params {
        if let syn::GenericParam::Type(held) = parameter {
            for bound in &held.bounds {
                beyond.visit_type_param_bound(bound);
            }
        }
    }
    if let Some(clause) = &signature.generics.where_clause {
        beyond.visit_where_clause(clause);
    }
    beyond.visit_block(body);
    let mut parameters = Beyond::default();
    for argument in &signature.inputs {
        if let FnArg::Typed(held) = argument {
            parameters.visit_type(&held.ty);
        }
    }
    Placed {
        returned: returns.names,
        receiver: signature
            .receiver()
            .and_then(syn::Receiver::lifetime)
            .map(|held| held.ident.to_string())
            .unwrap_or_default(),
        parameters: parameters.names,
        beyond: beyond.names,
    }
}

/// Every lifetime one piece of syntax names, which is what decides whether a declaration is idle.
#[derive(Default)]
struct Beyond {
    names: Vec<String>,
}

impl Visit<'_> for Beyond {
    fn visit_lifetime(&mut self, held: &syn::Lifetime) {
        self.names.push(held.ident.to_string());
    }
}

/// Walk one module for the three things it says about ownership.
impl Visit<'_> for Surface {
    fn visit_item_fn(&mut self, declared: &syn::ItemFn) {
        self.annotate(
            &declared.sig.generics,
            "function",
            &declared.sig.ident,
            placed(&declared.sig, &declared.block),
        );
        self.owners.push(format!("{}::", declared.sig.ident));
        syn::visit::visit_item_fn(self, declared);
        self.owners.pop();
    }

    fn visit_impl_item_fn(&mut self, declared: &syn::ImplItemFn) {
        self.annotate(
            &declared.sig.generics,
            "method",
            &declared.sig.ident,
            placed(&declared.sig, &declared.block),
        );
        self.owners.push(format!("{}::", declared.sig.ident));
        syn::visit::visit_impl_item_fn(self, declared);
        self.owners.pop();
    }

    fn visit_item_struct(&mut self, declared: &syn::ItemStruct) {
        self.annotate(
            &declared.generics,
            "type",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_struct(self, declared);
    }

    fn visit_item_enum(&mut self, declared: &syn::ItemEnum) {
        self.annotate(
            &declared.generics,
            "type",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_enum(self, declared);
    }

    fn visit_item_trait(&mut self, declared: &syn::ItemTrait) {
        self.annotate(
            &declared.generics,
            "trait",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_trait(self, declared);
    }

    fn visit_item_type(&mut self, declared: &syn::ItemType) {
        self.annotate(
            &declared.generics,
            "alias",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_type(self, declared);
    }

    fn visit_type_param_bound(&mut self, bound: &syn::TypeParamBound) {
        if let syn::TypeParamBound::Lifetime(held) = bound
            && held.ident == "static"
        {
            self.pins.push(json!({
                "owner": self.owner(),
                "line": held.ident.span().start().line,
                "position": "bound",
            }));
            return;
        }
        syn::visit::visit_type_param_bound(self, bound);
    }

    fn visit_lifetime(&mut self, held: &syn::Lifetime) {
        if held.ident == "static" {
            self.pins.push(json!({
                "owner": self.owner(),
                "line": held.ident.span().start().line,
                "position": if self.demanding { "demand" } else { "supply" },
            }));
        }
    }

    /// Walk a signature knowing which side of it each type sits on.
    ///
    /// A pin in a parameter is a demand on the caller and a pin in a return is a promise to it,
    /// and only one of those forecloses anything, so the two cannot be counted the same way.
    fn visit_signature(&mut self, signature: &Signature) {
        for argument in &signature.inputs {
            self.demanding = true;
            syn::visit::visit_fn_arg(self, argument);
            self.demanding = false;
        }
        syn::visit::visit_return_type(self, &signature.output);
        syn::visit::visit_generics(self, &signature.generics);
    }

    fn visit_field(&mut self, field: &syn::Field) {
        self.demanding = true;
        syn::visit::visit_field(self, field);
        self.demanding = false;
    }

    fn visit_expr_method_call(&mut self, call: &syn::ExprMethodCall) {
        if matches!(call.method.to_string().as_str(), "clone" | "to_owned") {
            self.clones.push(json!({
                "receiver": rendered_expression(&call.receiver),
                "owner": self.owner(),
                "line": call.method.span().start().line,
                "loop_depth": self.loop_depth,
            }));
        }
        syn::visit::visit_expr_method_call(self, call);
    }

    fn visit_expr_for_loop(&mut self, held: &syn::ExprForLoop) {
        self.loop_depth += 1;
        syn::visit::visit_expr_for_loop(self, held);
        self.loop_depth -= 1;
    }

    fn visit_expr_while(&mut self, held: &syn::ExprWhile) {
        self.loop_depth += 1;
        syn::visit::visit_expr_while(self, held);
        self.loop_depth -= 1;
    }

    fn visit_expr_loop(&mut self, held: &syn::ExprLoop) {
        self.loop_depth += 1;
        syn::visit::visit_expr_loop(self, held);
        self.loop_depth -= 1;
    }
}

/// Return the name one expression reads, which is what a copy of it is a copy of.
fn rendered_expression(expression: &syn::Expr) -> String {
    match expression {
        syn::Expr::Path(path) => path_name(&path.path),
        syn::Expr::Field(field) => match &field.member {
            syn::Member::Named(name) => {
                format!("{}.{name}", rendered_expression(&field.base))
            }
            syn::Member::Unnamed(index) => {
                format!("{}.{}", rendered_expression(&field.base), index.index)
            }
        },
        syn::Expr::MethodCall(call) => {
            format!("{}.{}()", rendered_expression(&call.receiver), call.method)
        }
        syn::Expr::Reference(inner) => rendered_expression(&inner.expr),
        syn::Expr::Paren(inner) => rendered_expression(&inner.expr),
        _ => String::new(),
    }
}

/// Return the span one piece of syntax covers, in the shape the Python models validate.
fn locate(source: &Source, span: Span) -> Value {
    let (start, end) = (span.start(), span.end());
    json!({
        "path": source.relative,
        "start_line": start.line,
        "start_column": start.column,
        "end_line": end.line,
        "end_column": end.column,
    })
}

fn base(source: &Source, key: &str, span: Span) -> Value {
    json!({"key": key, "span": locate(source, span), "language": "rust"})
}

fn merge(mut left: Value, right: Value) -> Value {
    if let (Some(target), Some(extra)) = (left.as_object_mut(), right.as_object()) {
        for (name, value) in extra {
            target.insert(name.clone(), value.clone());
        }
    }
    left
}

/// Return how widely one method of an `impl` block reaches.
///
/// A method satisfying a trait states no visibility of its own, because the trait already decided
/// one: wherever the trait is in scope the method is callable. Reading the missing keyword as
/// `private` would say a type implementing a public trait publishes nothing, which is the opposite
/// of what a trait implementation is for.
fn member_reach(block: &syn::ItemImpl, declared: &syn::Visibility) -> Visibility {
    match block.trait_.is_some() {
        true => Visibility::Public,
        false => visibility(declared),
    }
}

/// Return how widely one declaration reaches, by the way Rust states it.
fn visibility(declared: &syn::Visibility) -> Visibility {
    match declared {
        syn::Visibility::Public(_) => Visibility::Public,
        syn::Visibility::Restricted(restricted) => {
            if restricted.path.is_ident("crate") || restricted.path.is_ident("super") {
                Visibility::Internal
            } else {
                Visibility::Protected
            }
        }
        syn::Visibility::Inherited => Visibility::Private,
    }
}

fn label(reach: Visibility) -> &'static str {
    match reach {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Internal => "internal",
        Visibility::Private => "private",
    }
}

/// Return the name one declared item states, whatever kind of item it is.
fn declared_name(item: &Item) -> Option<String> {
    match item {
        Item::Struct(declared) => Some(declared.ident.to_string()),
        Item::Enum(declared) => Some(declared.ident.to_string()),
        Item::Union(declared) => Some(declared.ident.to_string()),
        Item::Trait(declared) => Some(declared.ident.to_string()),
        Item::Type(declared) => Some(declared.ident.to_string()),
        Item::Fn(declared) => Some(declared.sig.ident.to_string()),
        _ => None,
    }
}

fn is_type(item: &Item) -> bool {
    matches!(
        item,
        Item::Struct(_) | Item::Enum(_) | Item::Union(_) | Item::Trait(_)
    )
}

fn module_fact(source: &Source, file: &syn::File) -> Value {
    merge(
        base(
            source,
            &format!("module:{}", source.relative),
            Span::call_site(),
        ),
        json!({
            "physical_line_count": source.text.lines().count(),
            "class_count": file.items.iter().filter(|item| is_type(item)).count(),
            "function_count": file
                .items
                .iter()
                .filter(|item| matches!(item, Item::Fn(_)))
                .count(),
            "is_package_initializer": source.relative.ends_with("/mod.rs")
                || source.relative.ends_with("/lib.rs"),
            "members": file
                .items
                .iter()
                .filter_map(declared_name)
                .map(|name| json!({"name": name, "responsibility": ""}))
                .collect::<Vec<_>>(),
        }),
    )
}

fn import_facts(source: &Source, file: &syn::File) -> Vec<Value> {
    file.items
        .iter()
        .filter_map(|item| match item {
            Item::Use(declared) => Some(declared),
            _ => None,
        })
        .flat_map(|declared| {
            let public = matches!(declared.vis, syn::Visibility::Public(_));
            let span = declared.use_token.span;
            bindings(&declared.tree)
                .into_iter()
                .map(move |(bound, path)| (bound, path, public, span))
        })
        .map(|(bound, path, public, span)| {
            let references = source
                .text
                .matches(bound.as_str())
                .count()
                .saturating_sub(1);
            let root = path.split("::").next().unwrap_or(&path).to_string();
            let owned = matches!(root.as_str(), "crate" | "self" | "super");
            merge(
                base(source, &format!("import:{}:{bound}", source.relative), span),
                json!({
                    "name": bound,
                    "module": path,
                    "importer_module": source.relative.clone(),
                    "reference_count": references,
                    "has_qualifying_use": references > 0,
                    "is_relative": root == "self" || root == "super",
                    "is_project_owned": owned,
                    "is_external": !owned,
                    "is_reexported": public,
                }),
            )
        })
        .collect()
}

/// Return every name one use tree binds, with the path each one was bound to.
///
/// A use tree nests groups and renames around the names it finally binds, so `use a::{b, c as d}`
/// binds two names to two different paths and neither of them is written where it is bound.
fn bindings(tree: &UseTree) -> Vec<(String, String)> {
    fn walk(tree: &UseTree, prefix: &mut String, names: &mut Vec<(String, String)>) {
        match tree {
            UseTree::Path(path) => {
                let restore = prefix.len();
                if !prefix.is_empty() {
                    prefix.push_str("::");
                }
                prefix.push_str(&path.ident.to_string());
                walk(&path.tree, prefix, names);
                prefix.truncate(restore);
            }
            UseTree::Name(name) => names.push((name.ident.to_string(), prefix.clone())),
            UseTree::Rename(rename) => names.push((rename.rename.to_string(), prefix.clone())),
            UseTree::Glob(_) => names.push(("*".to_string(), prefix.clone())),
            UseTree::Group(group) => {
                for item in &group.items {
                    walk(item, prefix, names);
                }
            }
        }
    }
    let mut names = Vec::new();
    walk(tree, &mut String::new(), &mut names);
    names
}

fn function_facts(source: &Source, file: &syn::File) -> Vec<Value> {
    let mut facts = Vec::new();
    for item in &file.items {
        match item {
            Item::Fn(declared) => facts.push(function_fact(
                source,
                &declared.sig,
                visibility(&declared.vis),
                "module",
                Some(&declared.block),
            )),
            Item::Impl(block) => facts.extend(block.items.iter().filter_map(|member| {
                let ImplItem::Fn(method) = member else {
                    return None;
                };
                Some(function_fact(
                    source,
                    &method.sig,
                    member_reach(block, &method.vis),
                    "method",
                    Some(&method.block),
                ))
            })),
            Item::Trait(declared) => facts.extend(declared.items.iter().filter_map(|member| {
                let TraitItem::Fn(method) = member else {
                    return None;
                };
                Some(function_fact(
                    source,
                    &method.sig,
                    Visibility::Public,
                    "method",
                    method.default.as_ref(),
                ))
            })),
            _ => {}
        }
    }
    facts
}

fn function_fact(
    source: &Source,
    signature: &Signature,
    reach: Visibility,
    scope: &str,
    body: Option<&syn::Block>,
) -> Value {
    let name = signature.ident.to_string();
    let increments = body.map(control_increments).unwrap_or_default();
    merge(
        base(
            source,
            &format!("function:{}:{name}", source.relative),
            signature.ident.span(),
        ),
        json!({
            "name": name,
            "scope": scope,
            "visibility": label(reach),
            "is_async": signature.asyncness.is_some(),
            "implementation_lines": body.map_or(0, body_lines),
            "direct_statement_count": body.map_or(0, |held| held.stmts.len()),
            "conditional_count": increments
                .iter()
                .filter(|value| value["kind"] == "conditional")
                .count(),
            "control_increments": increments,
            "parameters": signature.inputs.iter().map(parameter_fact).collect::<Vec<_>>(),
        }),
    )
}

/// Return how many physical lines one body runs, from its first statement to its last.
///
/// The braces are left out because the signature is not the work, which is the same boundary the
/// reference frontend draws when it drops the declaration line and the docstring under it.
fn body_lines(body: &syn::Block) -> usize {
    let (Some(first), Some(last)) = (body.stmts.first(), body.stmts.last()) else {
        return 0;
    };
    last.span().end().line - first.span().start().line + 1
}

/// Return every control structure one body holds, each with the number enclosing it.
///
/// The kinds and the depth arithmetic are the reference frontend's, because the complexity and
/// nesting rules own one scoring model for every language and a second convention here would make
/// the same program measure differently depending on who wrote it. What genuinely differs is where
/// a language keeps its control flow. Python states it as statements, so its reader walks
/// statements; Rust states it as expressions, so a `match` bound to a name is the same structure as
/// a `match` standing on its own line and both have to be found.
fn control_increments(body: &syn::Block) -> Vec<Value> {
    let mut found = Control::default();
    found.visit_block(body);
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
    fn inside(&mut self, held: &syn::Block) {
        self.depth += 1;
        syn::visit::visit_block(self, held);
        self.depth -= 1;
    }

    /// Record one arm of a decision, which continues it rather than nesting inside it.
    ///
    /// `} else if {` is what this language spells `elif` with, so every arm of one chain sits at
    /// the depth the first `if` opened at. Reading the chain as a branch inside a branch would
    /// charge a reader a level of nesting the page never shows them.
    fn alternative(&mut self, otherwise: &syn::Expr) {
        self.record("alternative");
        match otherwise {
            syn::Expr::If(chained) => {
                syn::visit::visit_expr(self, &chained.cond);
                self.inside(&chained.then_branch);
                if let Some((_, next)) = &chained.else_branch {
                    self.alternative(next);
                }
            }
            syn::Expr::Block(held) => self.inside(&held.block),
            held => syn::visit::visit_expr(self, held),
        }
    }
}

impl Visit<'_> for Control {
    fn visit_expr_if(&mut self, held: &syn::ExprIf) {
        self.record("conditional");
        syn::visit::visit_expr(self, &held.cond);
        self.inside(&held.then_branch);
        if let Some((_, otherwise)) = &held.else_branch {
            self.alternative(otherwise);
        }
    }

    fn visit_expr_match(&mut self, held: &syn::ExprMatch) {
        self.record("switch");
        syn::visit::visit_expr(self, &held.expr);
        self.depth += 1;
        for arm in &held.arms {
            syn::visit::visit_expr(self, &arm.body);
        }
        self.depth -= 1;
    }

    fn visit_expr_for_loop(&mut self, held: &syn::ExprForLoop) {
        self.record("loop");
        syn::visit::visit_expr(self, &held.expr);
        self.inside(&held.body);
    }

    fn visit_expr_while(&mut self, held: &syn::ExprWhile) {
        self.record("loop");
        syn::visit::visit_expr(self, &held.cond);
        self.inside(&held.body);
    }

    fn visit_expr_loop(&mut self, held: &syn::ExprLoop) {
        self.record("loop");
        self.inside(&held.body);
    }

    /// A closure is a callable of its own and states its own fact, exactly as a nested `def` does.
    fn visit_expr_closure(&mut self, _: &syn::ExprClosure) {}

    /// A declaration written inside a body is a declaration, and the family reports it separately.
    fn visit_item(&mut self, _: &Item) {}
}

fn parameter_fact(argument: &FnArg) -> Value {
    match argument {
        FnArg::Receiver(_) => json!({
            "name": "self",
            "is_receiver": true,
            "is_required_by_external_contract": false,
        }),
        FnArg::Typed(typed) => json!({
            "name": match typed.pat.as_ref() {
                syn::Pat::Ident(ident) => ident.ident.to_string(),
                _ => String::new(),
            },
            "type_name": rendered(&typed.ty),
            "is_required_by_external_contract": true,
        }),
    }
}

/// Return the outermost name one type states, looking through the references around it.
fn rendered(declared: &Type) -> String {
    match declared {
        Type::Path(path) => path
            .path
            .segments
            .last()
            .map(|segment| segment.ident.to_string())
            .unwrap_or_default(),
        Type::Reference(inner) => rendered(&inner.elem),
        Type::Slice(inner) => rendered(&inner.elem),
        Type::Array(inner) => rendered(&inner.elem),
        Type::Paren(inner) => rendered(&inner.elem),
        Type::Group(inner) => rendered(&inner.elem),
        _ => String::new(),
    }
}

fn class_fact(source: &Source, file: &syn::File) -> Value {
    let mut methods: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut traits: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for item in &file.items {
        let Item::Impl(block) = item else { continue };
        let owner = rendered(&block.self_ty);
        if let Some((_, path, _)) = &block.trait_ {
            traits
                .entry(owner.clone())
                .or_default()
                .push(path_name(path));
        }
        for member in &block.items {
            let ImplItem::Fn(method) = member else {
                continue;
            };
            let receiver = method.sig.receiver().is_some();
            methods.entry(owner.clone()).or_default().push(json!({
                "name": method.sig.ident.to_string(),
                "kind": if receiver { "method" } else { "static_method" },
                "visibility": label(member_reach(block, &method.vis)),
            }));
        }
    }
    let classes: Vec<Value> = file
        .items
        .iter()
        .filter_map(|item| {
            let (name, reach, fields) = match item {
                Item::Struct(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.fields.len(),
                ),
                Item::Enum(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.variants.len(),
                ),
                Item::Union(declared) => (
                    declared.ident.to_string(),
                    visibility(&declared.vis),
                    declared.fields.named.len(),
                ),
                Item::Trait(declared) => {
                    (declared.ident.to_string(), visibility(&declared.vis), 0)
                }
                _ => return None,
            };
            Some(json!({
                "name": name.clone(),
                "path": source.relative.clone(),
                "scope": "module",
                "visibility": label(reach),
                "direct_bases": traits.get(&name).cloned().unwrap_or_default(),
                "methods": methods.get(&name).cloned().unwrap_or_default(),
                "field_count": fields,
                "has_instance_fields": fields > 0,
            }))
        })
        .collect();
    merge(
        base(
            source,
            &format!("classes:{}", source.relative),
            Span::call_site(),
        ),
        json!({"classes": classes}),
    )
}

/// Return one path as the `::` separated name the rest of the repository would write.
fn path_name(path: &syn::Path) -> String {
    path.segments
        .iter()
        .map(|segment| segment.ident.to_string())
        .collect::<Vec<_>>()
        .join("::")
}

/// Return every name one type states, including the ones its generic arguments hold.
///
/// `BTreeMap<String, Node>` depends on three names rather than one, so a generic argument is
/// opened rather than read as part of a single type. A type is a dependency with no other trace:
/// nothing calls it, constructs it, or inherits it, so without this edge the types a signature
/// names look unreached by everything.
fn type_names(declared: &Type) -> Vec<String> {
    match declared {
        Type::Path(path) => {
            let mut names = vec![path_name(&path.path)];
            for segment in &path.path.segments {
                let syn::PathArguments::AngleBracketed(arguments) = &segment.arguments else {
                    continue;
                };
                names.extend(arguments.args.iter().flat_map(|argument| match argument {
                    syn::GenericArgument::Type(inner) => type_names(inner),
                    _ => Vec::new(),
                }));
            }
            names
        }
        Type::Reference(inner) => type_names(&inner.elem),
        Type::Slice(inner) => type_names(&inner.elem),
        Type::Array(inner) => type_names(&inner.elem),
        Type::Paren(inner) => type_names(&inner.elem),
        Type::Group(inner) => type_names(&inner.elem),
        Type::Ptr(inner) => type_names(&inner.elem),
        Type::Tuple(tuple) => tuple.elems.iter().flat_map(type_names).collect(),
        Type::ImplTrait(item) => item.bounds.iter().flat_map(bound_names).collect(),
        Type::TraitObject(item) => item.bounds.iter().flat_map(bound_names).collect(),
        _ => Vec::new(),
    }
}

fn bound_names(bound: &syn::TypeParamBound) -> Vec<String> {
    match bound {
        syn::TypeParamBound::Trait(item) => vec![path_name(&item.path)],
        _ => Vec::new(),
    }
}

/// Return every trait one set of attributes derives, which the compiler then implements.
fn derives(attributes: &[syn::Attribute]) -> Vec<String> {
    let mut names = Vec::new();
    for attribute in attributes
        .iter()
        .filter(|attribute| attribute.path().is_ident("derive"))
    {
        let _ = attribute.parse_nested_meta(|derived| {
            names.push(path_name(&derived.path));
            Ok(())
        });
    }
    names
}

/// Build the part of the repository graph one Rust file states.
pub fn graph(source: Source, module: &str) -> Option<Stated> {
    let file = syn::parse_file(&source.text).ok()?;
    let mut collector = Collector::new(source, module.to_string());
    collector.items(&file.items);
    Some(Stated {
        nodes: collector.nodes,
        edges: collector.edges,
        references: collector.references,
        aliases: collector.aliases,
    })
}

/// What one named type promises its readers, which separates a contract from what satisfies it.
///
/// Rust draws this line sharply and in exactly one place. A trait states methods and provides no
/// data, so nothing can be built from it and every user of it is written against the promise; a
/// struct, an enum, a union, and an alias are all the thing itself.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Promise {
    Contract,
    Implementation,
}

/// Collect every definition and reference one Rust file states.
struct Collector {
    source: Source,
    scopes: Vec<String>,
    /// The modules open at this point, innermost last, which is what a relative path climbs.
    ///
    /// This is not the scope stack. A scope is any name that qualifies what sits inside it, so a
    /// type and a function body both push one, and `super` climbs modules rather than names.
    enclosing: Vec<String>,
    owners: Vec<String>,
    receiver: Option<String>,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    references: Vec<Reference>,
    aliases: BTreeMap<String, String>,
}

impl Collector {
    fn new(source: Source, module: String) -> Self {
        Self {
            source,
            owners: vec![identity(Language::Rust, NodeKind::Module, &module)],
            scopes: vec![module.clone()],
            enclosing: vec![module.clone()],
            receiver: None,
            nodes: Vec::new(),
            edges: Vec::new(),
            references: Vec::new(),
            aliases: BTreeMap::new(),
        }
    }

    fn scope(&self) -> String {
        self.scopes.last().cloned().unwrap_or_default()
    }

    fn owner(&self) -> String {
        self.owners.last().cloned().unwrap_or_default()
    }

    fn items(&mut self, items: &[Item]) {
        for item in items {
            self.item(item);
        }
    }

    /// State what one item declares, what it names, and what its body reaches.
    ///
    /// Every arm follows the same shape: declare the node, relate it to whatever holds it, record
    /// the types it names, then walk into whatever body it carries. The kinds differ only in which
    /// of those four an item actually has.
    fn item(&mut self, item: &Item) {
        match item {
            Item::Use(declared) => self.import(declared),
            Item::Mod(declared) => self.nested(declared),
            Item::Struct(declared) => {
                let id = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    Promise::Implementation,
                );
                for field in &declared.fields {
                    self.field(&id, field);
                }
            }
            Item::Union(declared) => {
                let id = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    Promise::Implementation,
                );
                for field in &declared.fields.named {
                    self.field(&id, field);
                }
            }
            Item::Enum(declared) => self.enumeration(declared),
            Item::Trait(declared) => self.contract(declared),
            Item::Type(declared) => {
                let id = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    Promise::Implementation,
                );
                self.types(&id, &declared.ty, declared.ident.span());
            }
            Item::Fn(declared) => {
                let qualname = format!("{}::{}", self.scope(), declared.sig.ident);
                let owner = self.owner();
                let id =
                    self.callable(&owner, &qualname, &declared.sig, visibility(&declared.vis));
                self.body(&id, &qualname, &declared.block);
            }
            Item::Impl(block) => self.implementation(block),
            Item::Const(declared) => {
                let id = self.constant(&declared.ident, &declared.vis);
                self.types(&id, &declared.ty, declared.ident.span());
                self.initializer(&id, &declared.expr);
            }
            Item::Static(declared) => {
                let id = self.constant(&declared.ident, &declared.vis);
                self.types(&id, &declared.ty, declared.ident.span());
                self.initializer(&id, &declared.expr);
            }
            _ => {}
        }
    }

    /// Walk into a module written inside this file, which its own name then qualifies.
    fn nested(&mut self, declared: &syn::ItemMod) {
        let Some((_, items)) = &declared.content else {
            return;
        };
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let mut held = node(Language::Rust, NodeKind::Module, &qualname);
        held.path = Some(self.source.relative.clone());
        held.line = Some(declared.ident.span().start().line);
        held.visibility = visibility(&declared.vis);
        let id = held.id.clone();
        self.declare(held, declared.ident.span());
        self.enclosing.push(qualname.clone());
        self.scopes.push(qualname);
        self.owners.push(id);
        self.items(items);
        self.owners.pop();
        self.scopes.pop();
        self.enclosing.pop();
    }

    /// Declare one enum, whose variants are the names the rest of the repository reads it by.
    fn enumeration(&mut self, declared: &syn::ItemEnum) {
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let id = self.datatype(
            &declared.ident,
            &declared.vis,
            &declared.attrs,
            Promise::Implementation,
        );
        for variant in &declared.variants {
            let mut member = node(
                Language::Rust,
                NodeKind::Attribute,
                &format!("{qualname}::{}", variant.ident),
            );
            member.path = Some(self.source.relative.clone());
            member.line = Some(variant.ident.span().start().line);
            let member_id = member.id.clone();
            self.nodes.push(member);
            self.relate(&id, &member_id, EdgeKind::Define, variant.ident.span());
            for field in &variant.fields {
                self.types(&id, &field.ty, variant.ident.span());
            }
        }
    }

    /// Declare one trait, the contract it extends, and every method it states.
    fn contract(&mut self, declared: &syn::ItemTrait) {
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let id = self.datatype(
            &declared.ident,
            &declared.vis,
            &declared.attrs,
            Promise::Contract,
        );
        for supertrait in &declared.supertraits {
            for name in bound_names(supertrait) {
                self.reference(&id, &name, EdgeKind::Inherit, declared.ident.span());
            }
        }
        for member in &declared.items {
            let TraitItem::Fn(method) = member else {
                continue;
            };
            let owned = format!("{qualname}::{}", method.sig.ident);
            let method_id = self.callable(&id, &owned, &method.sig, Visibility::Public);
            if let Some(body) = &method.default {
                self.body(&method_id, &owned, body);
            }
        }
    }

    /// Declare one named type, which is what a struct, an enum, a union, a trait, and an alias are.
    ///
    /// A derive is an implementation the compiler writes, so the type satisfies that trait exactly
    /// as it would with an impl block spelled out, and the graph says so.
    ///
    /// What the type promises travels with it, because a trait states a contract and provides none
    /// of it while every other item here is the implementation somebody has to write.
    fn datatype(
        &mut self,
        name: &syn::Ident,
        reach: &syn::Visibility,
        attributes: &[syn::Attribute],
        promise: Promise,
    ) -> String {
        let qualname = format!("{}::{name}", self.scope());
        let mut declared = node(Language::Rust, NodeKind::Class, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(name.span().start().line);
        declared.visibility = visibility(reach);
        declared.is_abstract = promise == Promise::Contract;
        let id = declared.id.clone();
        self.declare(declared, name.span());
        for derived in derives(attributes) {
            self.reference(&id, &derived, EdgeKind::Inherit, name.span());
        }
        id
    }

    fn constant(&mut self, name: &syn::Ident, reach: &syn::Visibility) -> String {
        let qualname = format!("{}::{name}", self.scope());
        let mut declared = node(Language::Rust, NodeKind::Variable, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(name.span().start().line);
        declared.visibility = visibility(reach);
        let id = declared.id.clone();
        self.declare(declared, name.span());
        id
    }

    fn field(&mut self, owner: &str, field: &syn::Field) {
        let span = field
            .ident
            .as_ref()
            .map_or_else(Span::call_site, |name| name.span());
        if let Some(name) = &field.ident {
            let holder = owner.rsplit(':').next().unwrap_or_default();
            let mut declared = node(
                Language::Rust,
                NodeKind::Attribute,
                &format!("{holder}::{name}"),
            );
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(span.start().line);
            declared.visibility = visibility(&field.vis);
            declared.annotation = Some(rendered(&field.ty));
            let id = declared.id.clone();
            self.nodes.push(declared);
            self.relate(owner, &id, EdgeKind::Define, span);
        }
        self.types(owner, &field.ty, span);
    }

    /// Declare one callable, the parameters it takes, and every type its signature names.
    fn callable(
        &mut self,
        owner: &str,
        qualname: &str,
        signature: &Signature,
        reach: Visibility,
    ) -> String {
        let kind = if owner.contains(":class:") {
            NodeKind::Method
        } else {
            NodeKind::Function
        };
        let mut declared = node(Language::Rust, kind, qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(signature.ident.span().start().line);
        declared.visibility = reach;
        declared.asynchronous = signature.asyncness.is_some();
        if let ReturnType::Type(_, returns) = &signature.output {
            declared.return_annotation = Some(rendered(returns));
        }
        let id = declared.id.clone();
        self.nodes.push(declared);
        self.relate(owner, &id, EdgeKind::Define, signature.ident.span());
        // Rust binds every argument by its position and offers no way to name one at a call site,
        // and it has no default argument either, so both facts a parameter carries beyond its
        // name are read off the language rather than left unstated.
        for (ordinal, argument) in signature.inputs.iter().enumerate() {
            let FnArg::Typed(typed) = argument else {
                continue;
            };
            let syn::Pat::Ident(name) = typed.pat.as_ref() else {
                continue;
            };
            let mut held = parameter(
                Language::Rust,
                &format!("{qualname}::{}", name.ident),
                ordinal,
                ParameterKind::PositionalOnly,
                false,
            );
            held.path = Some(self.source.relative.clone());
            held.line = Some(name.ident.span().start().line);
            held.annotation = Some(rendered(&typed.ty));
            let held_id = held.id.clone();
            self.nodes.push(held);
            self.relate(&id, &held_id, EdgeKind::Define, name.ident.span());
            self.types(&id, &typed.ty, name.ident.span());
        }
        if let ReturnType::Type(_, returns) = &signature.output {
            self.types(&id, returns, signature.ident.span());
        }
        id
    }

    /// State what one impl block adds to the type it names, and to the trait it satisfies.
    fn implementation(&mut self, block: &syn::ItemImpl) {
        let named = type_names(&block.self_ty);
        let Some(subject) = named.first() else {
            return;
        };
        let qualname = self.qualify(subject);
        let owner = identity(Language::Rust, NodeKind::Class, &qualname);
        if let Some((_, path, _)) = &block.trait_ {
            self.reference(
                &owner,
                &path_name(path),
                EdgeKind::Inherit,
                block.impl_token.span,
            );
        }
        for member in &block.items {
            let ImplItem::Fn(method) = member else {
                continue;
            };
            let held = format!("{qualname}::{}", method.sig.ident);
            // A trait method is as reachable as the trait itself, whatever the impl block writes,
            // since a caller reaches it through the trait rather than through the type.
            let reach = match block.trait_ {
                Some(_) => Visibility::Public,
                None => visibility(&method.vis),
            };
            let id = self.callable(&owner, &held, &method.sig, reach);
            self.receiver = Some(qualname.clone());
            self.body(&id, &held, &method.block);
            self.receiver = None;
        }
    }

    /// Return the repository-wide name one written type name stands for.
    fn qualify(&self, written: &str) -> String {
        match self.aliases.get(written) {
            Some(target) => target.clone(),
            None => format!("{}::{written}", self.scope()),
        }
    }

    fn declare(&mut self, declared: Node, span: Span) {
        let owner = self.owner();
        let id = declared.id.clone();
        self.nodes.push(declared);
        self.relate(&owner, &id, EdgeKind::Define, span);
    }

    fn types(&mut self, owner: &str, declared: &Type, span: Span) {
        for name in type_names(declared) {
            self.reference(owner, &name, EdgeKind::Typed, span);
        }
    }

    /// Record every import one use declaration states, and what each binding now names.
    fn import(&mut self, declared: &syn::ItemUse) {
        let owner = self.owner();
        for (bound, path) in bindings(&declared.tree) {
            let target = self.absolute(&path);
            let reached = format!("{target}::{bound}");
            self.aliases.insert(
                bound.clone(),
                if bound == "*" {
                    target.clone()
                } else {
                    reached.clone()
                },
            );
            self.references.push(Reference {
                source: owner.clone(),
                // A `use` names the module it reaches through, and only resolution knows how much
                // of the path is one. Handing over everything the line wrote lets the walk down
                // the path stop at the deepest module, so `use crate::families` reaches that
                // module rather than the crate root that merely holds it.
                expression: if bound == "*" {
                    target
                } else {
                    reached.clone()
                },
                language: Language::Rust,
                module: self.scope(),
                owner: None,
                receiver_type: None,
                kind: EdgeKind::Import,
                path: self.source.relative.clone(),
                line: declared.use_token.span.start().line,
            });
            // The import edge names the module it resolved to. A module that re-exports a symbol
            // reaches that symbol, and nothing else records it.
            if bound != "*" {
                self.reference(&owner, &reached, EdgeKind::Access, declared.use_token.span);
            }
        }
    }

    /// Return the repository-wide path one written path stands for.
    ///
    /// Rust writes a path from where it is read. `crate` is the crate root, `self` is this module,
    /// and each `super` climbs one. Rewriting all three against the module doing the reading is
    /// what lets one repository-wide table answer for every file in it.
    ///
    /// The module doing the reading is the innermost one that is open, not the file. A `mod tests`
    /// writing `use super::*` names the file around it, and climbing from the file instead would
    /// send every test module in the crate at the crate root.
    fn absolute(&self, written: &str) -> String {
        let reader = self.enclosing.last().cloned().unwrap_or_default();
        let mut segments = written.split("::");
        let head = segments.next().unwrap_or_default();
        let rest: Vec<&str> = segments.collect();
        let mut owner: Vec<&str> = reader.split("::").collect();
        let mut climbed = match head {
            "crate" => vec![*owner.first().unwrap_or(&"crate")],
            "self" => owner,
            "super" => {
                owner.pop();
                owner
            }
            _ => return written.to_string(),
        };
        let mut remaining = rest.as_slice();
        while remaining.first() == Some(&"super") {
            climbed.pop();
            remaining = &remaining[1..];
        }
        climbed
            .into_iter()
            .chain(remaining.iter().copied())
            .collect::<Vec<_>>()
            .join("::")
    }

    fn body(&mut self, owner: &str, qualname: &str, block: &syn::Block) {
        self.owners.push(owner.to_string());
        self.scopes.push(qualname.to_string());
        self.visit_block(block);
        self.scopes.pop();
        self.owners.pop();
    }

    /// Walk what a constant is set to, which is a table of real functions often enough to matter.
    fn initializer(&mut self, owner: &str, value: &syn::Expr) {
        self.owners.push(owner.to_string());
        self.visit_expr(value);
        self.owners.pop();
    }

    fn relate(&mut self, source: &str, target: &str, kind: EdgeKind, span: Span) {
        self.edges.push(Edge {
            source: source.to_string(),
            target: target.to_string(),
            kind,
            path: self.source.relative.clone(),
            line: span.start().line,
            resolution: Resolution::Exact,
        });
    }

    fn reference(&mut self, source: &str, expression: &str, kind: EdgeKind, span: Span) {
        if expression.is_empty() {
            return;
        }
        self.references.push(Reference {
            source: source.to_string(),
            expression: self.absolute(expression),
            language: Language::Rust,
            module: self.scope(),
            owner: self.receiver.clone(),
            receiver_type: None,
            kind,
            path: self.source.relative.clone(),
            line: span.start().line,
        });
    }
}

/// Walk what a body does, which is where every call, construction, and member read is stated.
///
/// Only the expressions that name something outside themselves are recorded. A bare identifier is
/// almost always a local, so a path earns an edge once it carries a qualifier, which is exactly
/// when it names something another module declared.
impl Visit<'_> for Collector {
    fn visit_expr_call(&mut self, call: &syn::ExprCall) {
        match call.func.as_ref() {
            syn::Expr::Path(path) => {
                let owner = self.owner();
                let span = path
                    .path
                    .segments
                    .last()
                    .map_or_else(Span::call_site, |segment| segment.ident.span());
                self.reference(&owner, &path_name(&path.path), EdgeKind::Call, span);
            }
            other => self.visit_expr(other),
        }
        for argument in &call.args {
            self.visit_expr(argument);
        }
    }

    fn visit_expr_method_call(&mut self, call: &syn::ExprMethodCall) {
        let reached = match call.receiver.as_ref() {
            syn::Expr::Path(path) if path.path.is_ident("self") => self
                .receiver
                .clone()
                .map(|kind| format!("{kind}::{}", call.method)),
            _ => None,
        };
        if let Some(reached) = reached {
            let owner = self.owner();
            self.reference(&owner, &reached, EdgeKind::Call, call.method.span());
        }
        self.visit_expr(&call.receiver);
        for argument in &call.args {
            self.visit_expr(argument);
        }
    }

    fn visit_expr_struct(&mut self, literal: &syn::ExprStruct) {
        let owner = self.owner();
        self.reference(
            &owner,
            &path_name(&literal.path),
            EdgeKind::Call,
            literal.brace_token.span.join(),
        );
        for field in &literal.fields {
            self.visit_expr(&field.expr);
        }
    }

    fn visit_expr_path(&mut self, read: &syn::ExprPath) {
        if read.path.segments.len() < 2 {
            return;
        }
        let owner = self.owner();
        let span = read
            .path
            .segments
            .last()
            .map_or_else(Span::call_site, |segment| segment.ident.span());
        self.reference(&owner, &path_name(&read.path), EdgeKind::Access, span);
    }

    fn visit_type(&mut self, declared: &Type) {
        let owner = self.owner();
        self.types(&owner, declared, Span::call_site());
    }

    fn visit_item(&mut self, item: &Item) {
        self.item(item);
    }
}

/// Resolve one Rust reference against the repository, leaving what cannot be proved visible.
///
/// A path arrives already rewritten against the module that wrote it, so resolution is mostly
/// asking whether the repository declares the name. What remains is the two ways a written name
/// is shorter than what it means: a `use` bound it to something longer, and a nested module sees
/// every name its ancestors hold.
pub fn resolve(
    reference: &Reference,
    reachable: &BTreeSet<String>,
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    nodes: &mut BTreeMap<String, Node>,
    edges: &mut Vec<Edge>,
) {
    let expanded = expanded(aliases, &reference.module, &reference.expression);
    let mut candidates = Vec::new();
    if reference.kind == EdgeKind::Import {
        let parts: Vec<&str> = expanded.split("::").collect();
        candidates.extend((1..=parts.len()).rev().map(|size| parts[..size].join("::")));
    } else {
        candidates.extend([expanded.clone(), reference.expression.clone()]);
        if let Some(owner) = &reference.owner {
            candidates.push(format!("{owner}::{expanded}"));
        }
        let mut scope: Vec<&str> = reference.module.split("::").collect();
        while !scope.is_empty() {
            candidates.push(format!("{}::{expanded}", scope.join("::")));
            scope.pop();
        }
    }
    if attach(reference, &candidates, reachable, nodes, edges) {
        return;
    }
    let head = expanded.split("::").next().unwrap_or(&expanded);
    let (kind, qualname) = match reference.kind {
        EdgeKind::Import => (NodeKind::ExternalModule, head.to_string()),
        _ if is_provided(head) => (NodeKind::ExternalSymbol, format!("core::{expanded}")),
        _ if expanded.contains("::") => (NodeKind::ExternalSymbol, expanded),
        _ => (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", reference.module, reference.expression),
        ),
    };
    stray(reference, kind, &qualname, nodes, edges);
}

/// Return one written path with its leading name replaced by whatever a `use` bound it to.
///
/// The bindings that answer live in the nearest enclosing module that stated any, since a nested
/// module sees what its ancestors imported. Asking that question and rewriting the path are one
/// step for the caller, so they are one function here and no table is handed back to borrow.
fn expanded(
    aliases: &BTreeMap<String, BTreeMap<String, String>>,
    module: &str,
    expression: &str,
) -> String {
    let (head, rest) = expression.split_once("::").unwrap_or((expression, ""));
    let mut scope: Vec<&str> = module.split("::").collect();
    while !scope.is_empty() {
        if let Some(target) = aliases
            .get(&scope.join("::"))
            .and_then(|held| held.get(head))
        {
            return match rest.is_empty() {
                true => target.clone(),
                false => format!("{target}::{rest}"),
            };
        }
        scope.pop();
    }
    expression.to_string()
}

/// Whether one name is something the language itself provides rather than a crate.
fn is_provided(name: &str) -> bool {
    const NAMES: &[&str] = &[
        "bool",
        "char",
        "f32",
        "f64",
        "i8",
        "i16",
        "i32",
        "i64",
        "i128",
        "isize",
        "str",
        "u8",
        "u16",
        "u32",
        "u64",
        "u128",
        "usize",
        "String",
        "Vec",
        "Option",
        "Some",
        "None",
        "Result",
        "Ok",
        "Err",
        "Box",
        "Self",
        "self",
        "Iterator",
        "Default",
        "Clone",
        "Copy",
        "Debug",
        "PartialEq",
        "Eq",
        "PartialOrd",
        "Ord",
        "Hash",
        "From",
        "Into",
        "TryFrom",
        "TryInto",
        "AsRef",
        "Drop",
        "Fn",
        "FnMut",
        "FnOnce",
        "Send",
        "Sync",
        "Sized",
        "ToString",
    ];
    NAMES.contains(&name)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts_for(source: &str, family: &str) -> Vec<Value> {
        let document = Document {
            relative: "src/engine.rs".to_string(),
            source: source.to_string(),
        };
        let mut facts = BTreeMap::from([(family.to_string(), Vec::new())]);
        extract(&document, &mut facts, &mut Stats::default());
        facts.remove(family).unwrap_or_default()
    }

    fn graph_of(source: &str) -> crate::graph::Graph {
        crate::graph::build(
            "repo",
            &[
                Document {
                    relative: "kernel/src/main.rs".to_string(),
                    source: "mod engine;\n".to_string(),
                },
                Document {
                    relative: "kernel/src/engine.rs".to_string(),
                    source: source.to_string(),
                },
            ],
        )
    }

    #[test]
    fn pub_is_what_public_means_in_this_language() {
        let facts = facts_for(
            "pub fn build(name: &str) -> String { name.to_string() }\nfn helper() -> usize { 1 }\npub(crate) fn shared() -> usize { 2 }\n",
            "FunctionFact",
        );

        assert_eq!(facts[0]["name"], "build");
        assert_eq!(facts[0]["visibility"], "public");
        assert_eq!(facts[1]["visibility"], "private");
        assert_eq!(facts[2]["visibility"], "internal");
    }

    #[test]
    fn an_impl_block_carries_the_methods_of_the_type_it_names() {
        let facts = facts_for(
            "pub struct Engine { limit: usize }\n\nimpl Engine {\n    pub fn new() -> Self { Self { limit: 3 } }\n    fn run(&self) -> usize { self.limit }\n}\n\nimpl Default for Engine {\n    fn default() -> Self { Self::new() }\n}\n",
            "ClassFact",
        );
        let classes = facts[0]["classes"].as_array().unwrap();

        assert_eq!(classes[0]["name"], "Engine");
        assert_eq!(classes[0]["visibility"], "public");
        assert_eq!(classes[0]["field_count"], 1);
        assert_eq!(classes[0]["direct_bases"][0], "Default");
        let methods = classes[0]["methods"].as_array().unwrap();
        assert_eq!(methods[0]["kind"], "static_method");
        assert_eq!(methods[1]["kind"], "method");
        assert_eq!(methods[1]["visibility"], "private");
    }

    #[test]
    fn a_use_tree_binds_every_name_its_groups_and_renames_hold() {
        let facts = facts_for(
            "use crate::source::{Source, Span as Range};\nuse serde_json::Value;\n\npub fn run(value: Value, span: Range, source: Source) {}\n",
            "ImportBindingFact",
        );
        let names: Vec<&str> = facts
            .iter()
            .map(|fact| fact["name"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(names, vec!["Source", "Range", "Value"]);
        assert_eq!(facts[0]["module"], "crate::source");
        assert_eq!(facts[0]["is_project_owned"], true);
        assert_eq!(facts[2]["is_external"], true);
    }

    #[test]
    fn a_module_counts_the_types_and_callables_it_declares() {
        let facts = facts_for(
            "pub struct One;\npub enum Two { A }\npub trait Three {}\npub fn run() {}\n",
            "ModuleFact",
        );

        assert_eq!(facts[0]["class_count"], 3);
        assert_eq!(facts[0]["function_count"], 1);
    }

    #[test]
    fn a_crate_names_its_modules_from_the_directory_that_holds_its_root() {
        let graph = graph_of("pub struct Engine;\n");

        assert!(
            graph
                .nodes
                .iter()
                .any(|node| node.id == "rust:class:kernel::engine::Engine")
        );
    }

    #[test]
    fn a_field_and_a_signature_state_the_types_they_depend_on() {
        let graph = graph_of(
            "pub struct Budget;\npub struct Tally;\npub struct Report;\npub struct Holder { limit: Budget }\n\npub fn run(count: Tally) -> Report { Report }\n",
        );
        let typed: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Typed)
            .map(|edge| edge.target.as_str())
            .collect();

        assert!(typed.contains(&"rust:class:kernel::engine::Budget"));
        assert!(typed.contains(&"rust:class:kernel::engine::Tally"));
        assert!(typed.contains(&"rust:class:kernel::engine::Report"));
    }

    #[test]
    fn every_parameter_this_language_takes_binds_by_position_and_carries_no_default() {
        let graph = graph_of("pub fn run(count: usize, label: &str) -> usize { count }\n");
        let stated: Vec<(&str, Option<ParameterKind>, bool)> = graph
            .nodes
            .iter()
            .filter(|node| node.kind == NodeKind::Parameter)
            .map(|node| {
                (
                    node.qualname.as_str(),
                    node.parameter_kind,
                    node.has_default,
                )
            })
            .collect();

        assert_eq!(
            stated,
            vec![
                (
                    "kernel::engine::run::count",
                    Some(ParameterKind::PositionalOnly),
                    false
                ),
                (
                    "kernel::engine::run::label",
                    Some(ParameterKind::PositionalOnly),
                    false
                ),
            ]
        );
    }

    #[test]
    fn a_trait_impl_inherits_the_trait_it_satisfies() {
        let graph = graph_of(
            "pub struct Engine;\npub trait Runner {}\n\nimpl Runner for Engine {\n    fn go(&self) {}\n}\n",
        );

        assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Inherit
            && edge.source == "rust:class:kernel::engine::Engine"
            && edge.target == "rust:class:kernel::engine::Runner"));
    }

    #[test]
    fn a_call_and_a_construction_reach_what_this_crate_declares() {
        let graph = graph_of(
            "pub struct Engine { limit: usize }\n\npub fn helper() -> usize { 1 }\n\npub fn run() -> Engine {\n    let value = helper();\n    Engine { limit: value }\n}\n",
        );

        assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Call
            && edge.target == "rust:function:kernel::engine::helper"));
        assert!(
            graph
                .edges
                .iter()
                .any(|edge| edge.kind == EdgeKind::Instantiate
                    && edge.target == "rust:class:kernel::engine::Engine")
        );
    }

    #[test]
    fn an_annotation_states_every_position_it_names_a_lifetime_in() {
        let facts = facts_for(
            concat!(
                "pub fn only_inputs<'a>(left: &'a str, right: &'a str) -> usize { 0 }\n",
                "pub struct Holder { text: String }\n",
                "impl Holder {\n",
                "    pub fn name<'a>(&'a self, other: &str) -> &'a str { &self.text }\n",
                "    pub fn pick<'a>(&self, other: &'a str) -> &'a str { other }\n",
                "}\n",
                "pub fn from_one<'a>(node: Node<'a>, kind: &str) -> Option<&'a str> { None }\n",
            ),
            "RustSurfaceFact",
        );
        let placed: Vec<&Value> = facts[0]["annotations"].as_array().unwrap().iter().collect();

        assert_eq!(placed[0]["owner"], "only_inputs");
        assert!(placed[0]["returned"].as_array().unwrap().is_empty());
        assert_eq!(placed[1]["owner"], "name");
        assert_eq!(placed[1]["receiver"], "a");
        assert_eq!(placed[1]["returned"][0], "a");
        assert!(placed[1]["parameters"].as_array().unwrap().is_empty());
        assert_eq!(placed[2]["owner"], "pick");
        assert_eq!(placed[2]["receiver"], "");
        assert_eq!(placed[2]["parameters"][0], "a");
        assert_eq!(placed[3]["owner"], "from_one");
        assert_eq!(placed[3]["receiver"], "");
        assert_eq!(placed[3]["returned"][0], "a");
    }

    #[test]
    fn a_pinned_reference_is_told_apart_from_a_bound_and_a_copy_from_a_loop() {
        let facts = facts_for(
            concat!(
                "pub struct Report { title: &'static str }\n",
                "pub fn spawn<T: Send + 'static>(value: T) {}\n",
                "pub fn run(items: Vec<String>, prefix: String) -> Vec<String> {\n",
                "    let owned = prefix.clone();\n",
                "    for item in items {\n",
                "        registry.insert(prefix.clone(), item);\n",
                "    }\n",
                "    Vec::new()\n",
                "}\n",
            ),
            "RustSurfaceFact",
        );
        let pins = facts[0]["pins"].as_array().unwrap();
        let clones = facts[0]["clones"].as_array().unwrap();

        assert_eq!(pins.len(), 2);
        assert_eq!(
            pins.iter()
                .filter(|pin| pin["position"] == "demand")
                .count(),
            1
        );
        assert_eq!(pins[0]["position"], "demand");
        assert_eq!(clones.len(), 2);
        assert_eq!(clones[0]["loop_depth"], 0);
        assert_eq!(clones[1]["loop_depth"], 1);
        assert_eq!(clones[1]["receiver"], "prefix");
        assert_eq!(clones[1]["owner"], "run::");
    }

    #[test]
    fn a_pin_demands_in_a_parameter_and_only_promises_in_a_return() {
        let facts = facts_for(
            concat!(
                "pub fn label(kind: usize) -> &'static str { \"rust\" }\n",
                "pub fn describe(name: &'static str) -> usize { name.len() }\n",
            ),
            "RustSurfaceFact",
        );
        let pins = facts[0]["pins"].as_array().unwrap();

        assert_eq!(pins.len(), 2);
        assert_eq!(pins[0]["position"], "supply");
        assert_eq!(pins[1]["position"], "demand");
    }

    #[test]
    fn a_path_climbs_the_way_the_module_reading_it_would() {
        let collector = Collector::new(
            Source::new("kernel/src/graph/walk.rs", ""),
            "kernel::graph::walk".to_string(),
        );

        assert_eq!(collector.absolute("crate::source"), "kernel::source");
        assert_eq!(
            collector.absolute("self::inner"),
            "kernel::graph::walk::inner"
        );
        assert_eq!(
            collector.absolute("super::builder"),
            "kernel::graph::builder"
        );
        assert_eq!(collector.absolute("serde_json::Value"), "serde_json::Value");
    }

    #[test]
    fn a_nested_module_climbs_from_itself_rather_than_from_the_file_around_it() {
        let graph = graph_of(
            "pub fn build() -> usize {\n    1\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn it_builds() {\n        assert_eq!(build(), 1);\n    }\n}\n",
        );
        let reached: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import)
            .map(|edge| edge.target.as_str())
            .collect();

        assert_eq!(reached, ["rust:module:kernel::engine"]);
    }

    #[test]
    fn importing_a_module_by_name_reaches_that_module_and_not_the_one_holding_it() {
        let graph = crate::graph::build(
            "repo",
            &[
                Document {
                    relative: "kernel/src/main.rs".to_string(),
                    source: "mod codec;\nmod engine;\n".to_string(),
                },
                Document {
                    relative: "kernel/src/codec.rs".to_string(),
                    source: "pub struct Frame;\n".to_string(),
                },
                Document {
                    relative: "kernel/src/engine.rs".to_string(),
                    source: "use crate::codec;\n\npub fn build() -> codec::Frame {\n    codec::Frame\n}\n".to_string(),
                },
            ],
        );
        let reached: Vec<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Import)
            .map(|edge| edge.target.as_str())
            .collect();

        assert_eq!(reached, ["rust:module:kernel::codec"]);
    }

    /// Return every comment group one source states, which is what the family carries.
    fn groups_for(source: &str) -> Vec<Value> {
        let facts = facts_for(source, "CommentFact");
        facts[0]["groups"].as_array().cloned().unwrap_or_default()
    }

    #[test]
    fn every_way_this_language_opens_a_comment_reaches_the_family() {
        let groups = groups_for(concat!(
            "//! what this module is\n",
            "\n",
            "/// what this function does\n",
            "fn run() -> usize {\n",
            "    /* a held note */\n",
            "    1\n",
            "}\n",
        ));
        let said: Vec<&str> = groups
            .iter()
            .map(|group| group["node"]["text"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(
            said,
            vec![
                "//! what this module is",
                "/// what this function does",
                "/* a held note */"
            ]
        );
        assert_eq!(groups[0]["line_count"], 1);
        assert_eq!(groups[0]["token_count"], 5);
        assert_eq!(groups[0]["character_count"], 23);
    }

    #[test]
    fn commented_out_rust_is_told_apart_from_prose_about_it() {
        let groups = groups_for(concat!(
            "fn run(path: &str) -> usize {\n",
            "    // let stale = read(path);\n",
            "    // let parsed = parse(stale);\n",
            "\n",
            "    // retry twice before giving up\n",
            "    path.len()\n",
            "}\n",
            "\n",
            "// fn dead(value: usize) -> usize {\n",
            "//     value + 1\n",
            "// }\n",
        ));
        let read: Vec<(bool, i64)> = groups
            .iter()
            .map(|group| {
                (
                    group["parses_as_source"].as_bool().unwrap_or_default(),
                    group["line_count"].as_i64().unwrap_or_default(),
                )
            })
            .collect();

        // Statements and a whole declaration are both source; the sentence between them is not.
        assert_eq!(read, vec![(true, 2), (false, 1), (true, 3)]);
    }

    #[test]
    fn a_comment_marker_inside_a_literal_is_text_rather_than_a_comment() {
        let groups = groups_for(concat!(
            "fn run() -> usize {\n",
            "    let url = \"https://example.com/a//b\";\n",
            "    let held = 'x';\n",
            "    let raw = r#\"a /* still text */ b\"#;\n",
            "    /* the only note /* and the one it nests */ here */\n",
            "    url.len() + held.len_utf8() + raw.len()\n",
            "}\n",
        ));

        assert_eq!(groups.len(), 1);
        assert_eq!(
            groups[0]["node"]["text"],
            "/* the only note /* and the one it nests */ here */"
        );
    }

    /// A source is a `str`, so the scanner has to step characters rather than bytes.
    ///
    /// A cursor advancing one byte at a time lands inside any character wider than ASCII, and the
    /// next slice off it panics and takes the whole run down. Every place a wide character can be
    /// written is here at once, since each of them reaches the scanner through a different arm.
    #[test]
    fn a_source_written_outside_ascii_is_read_rather_than_crashed_on() {
        let groups = groups_for(concat!(
            "/* la mesa está aquí */\n",
            "fn café(entrée: &str) -> usize {\n",
            "    let señal = 'é';\n",
            "    let frase = \"até logo\";\n",
            "    // la señal está aquí\n",
            "    entrée.len() + frase.len() + señal.len_utf8()\n",
            "}\n",
        ));
        let said: Vec<&str> = groups
            .iter()
            .map(|group| group["node"]["text"].as_str().unwrap_or_default())
            .collect();

        assert_eq!(
            said,
            vec!["/* la mesa está aquí */", "// la señal está aquí"]
        );
    }

    /// A string that both escapes a quote and holds wide characters stays one literal.
    #[test]
    fn an_escaped_quote_beside_a_wide_character_never_swallows_the_comment_after_it() {
        let groups = groups_for(concat!(
            "fn run() -> usize {\n",
            "    let held = \"até \\\"logo\\\" // não\";\n",
            "    // the only note in this file\n",
            "    held.len()\n",
            "}\n",
        ));

        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0]["node"]["text"], "// the only note in this file");
    }

    /// A lifetime and a character literal open the same way and close differently.
    #[test]
    fn a_lifetime_is_stepped_past_where_a_character_literal_is_read_to_its_close() {
        let groups = groups_for(concat!(
            "fn head<'a>(text: &'a str) -> &'a str {\n",
            "    let marker = '/';\n",
            "    let wide = '中';\n",
            "    let escaped = '\\u{1F600}';\n",
            "    // the only note in this file\n",
            "    text\n",
            "}\n",
        ));

        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0]["node"]["text"], "// the only note in this file");
    }

    #[test]
    fn a_tool_switch_is_marked_and_never_absorbed_into_the_prose_beside_it() {
        let groups = groups_for("// rustfmt::skip\n// what this really does\nfn run() {}\n");

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["is_directive"], true);
        assert_eq!(groups[0]["parses_as_source"], false);
        assert_eq!(groups[1]["is_directive"], false);
    }

    #[test]
    fn a_work_marker_survives_into_the_text_the_general_rule_reads() {
        let groups = groups_for(concat!(
            "// TODO: handle the empty case\n",
            "fn load(path: &str) -> usize {\n",
            "    path.len() // FIXME: this loses the encoding\n",
            "}\n",
        ));
        let said: String = groups
            .iter()
            .map(|group| group["node"]["text"].as_str().unwrap_or_default())
            .collect();

        assert!(said.contains("TODO"));
        assert!(said.contains("FIXME"));
    }

    /// The shared vocabulary, the depth arithmetic, and the chain rule, all at once.
    ///
    /// The same program written for the reference frontend has to produce the same records, since
    /// the complexity and nesting rules own one scoring model for every language. What this
    /// language spells differently is only where the structure lives: a `match` bound to a name is
    /// a structure and a closure is a callable of its own.
    #[test]
    fn control_increments_record_their_nesting_depth() {
        let facts = facts_for(
            concat!(
                "pub fn run(items: Vec<Vec<usize>>) -> usize {\n",
                "    for item in items {\n",
                "        if item.is_empty() {\n",
                "            return 0;\n",
                "        } else if item.len() > 2 {\n",
                "            return 1;\n",
                "        } else {\n",
                "            return 2;\n",
                "        }\n",
                "    }\n",
                "    let picked = match 0 {\n",
                "        0 => 0,\n",
                "        _ => 1,\n",
                "    };\n",
                "    let held = |value: usize| if value > 0 { 1 } else { 0 };\n",
                "    picked + held(1)\n",
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
        assert_eq!(facts[0]["implementation_lines"], 15);
    }

    #[test]
    fn a_call_says_whether_anything_took_its_result() {
        let facts = facts_for(
            concat!(
                "pub fn run(values: Vec<usize>) -> usize {\n",
                "    record(values.len());\n",
                "    let total = sum(&values);\n",
                "    total\n",
                "}\n",
            ),
            "CallFact",
        );
        let called: Vec<(&str, bool)> = facts[0]["calls"]
            .as_array()
            .unwrap()
            .iter()
            .map(|call| {
                (
                    call["qualified_name"].as_str().unwrap_or_default(),
                    call["result_is_discarded"].as_bool().unwrap_or_default(),
                )
            })
            .collect();

        assert_eq!(
            called,
            vec![("record", true), ("len", false), ("sum", false)]
        );
        assert_eq!(facts[0]["module_bindings"][0], "run");
    }
}
