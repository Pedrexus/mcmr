use super::tokens::{Alphabet, DEDENT, IDENTIFIER, INDENT, NUMBER, TABLE, TEXT, TRUTH, Token};
use crate::discovery::Document;
use crate::graph::Language;
use proc_macro2::{Delimiter, TokenStream, TokenTree};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::ops::Range;
use std::str::FromStr;
use syn::spanned::Spanned;
use syn::visit::Visit;

mod brace;
mod hashing;
mod python;
mod records;
mod rust_docs;

pub(super) use brace::braces;
use hashing::{Delimiters, fingerprint, nesting};
use python::{implementation_lines as python_implementation_lines, python};
use records::StreamTokens;
pub(super) use records::{Fragment, Stream};
use rust_docs::documents;

impl Fragment {
    pub(super) fn value(&self, sources: &HashMap<&str, &str>) -> Value {
        let source = sources
            .get(self.path.as_str())
            .map(|text| {
                text.lines()
                    .skip(self.start_line - 1)
                    .take(self.end_line - self.start_line + 1)
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        json!({
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source": source,
        })
    }
}

impl Stream {
    /// Reduce one document, through the reader its language needs.
    pub(super) fn read(document: &Document, alphabet: &mut Alphabet) -> Option<Self> {
        let language = Language::of(&document.relative)?;
        let tokens = match language {
            Language::Python => python(document, alphabet),
            Language::Rust => rust(document, alphabet),
            Language::TypeScript | Language::C | Language::Cpp | Language::Cuda => {
                braces(document, alphabet)
            }
        }?;
        let symbols: Vec<u32> = tokens.iter().map(|token| token.symbol).collect();
        let (open, close) = match language {
            Language::Python => (alphabet.id(INDENT), alphabet.id(DEDENT)),
            Language::Rust
            | Language::TypeScript
            | Language::C
            | Language::Cpp
            | Language::Cuda => (alphabet.id("{"), alphabet.id("}")),
        };
        let depths = nesting(&symbols, Delimiters { open, close })?;
        let implementation_lines = match language {
            Language::Python => python_implementation_lines(document)?,
            Language::Rust => rust_implementation_lines(document)?,
            _ => Vec::new(),
        };
        let fingerprints = fingerprint(&symbols);
        let lines = tokens.iter().map(|token| token.line).collect();
        let identities = tokens.into_iter().map(|token| token.identity).collect();
        Some(Self {
            path: document.relative.clone(),
            language,
            tokens: StreamTokens {
                symbols,
                identities,
                lines,
                depths,
                fingerprints,
            },
            implementation_lines,
            block_open: open,
            table_plan: alphabet.id(TABLE),
            line_count: document.source.lines().count(),
        })
    }

    pub(super) fn fragment(&self, range: Range<usize>) -> Fragment {
        let (start_line, end_line) = self.line_range(range);
        Fragment {
            path: self.path.clone(),
            start_line,
            end_line,
        }
    }

    /// Return the alpha-renaming pattern of identifiers in one candidate range.
    pub(super) fn identity_pattern(&self, range: Range<usize>) -> Vec<u32> {
        let mut names: HashMap<&str, u32> = HashMap::new();
        self.tokens.identities[range]
            .iter()
            .map(|identity| {
                let Some(name) = identity.as_deref() else {
                    return 0;
                };
                let next =
                    u32::try_from(names.len() + 1).expect("clone identity pattern exceeded u32");
                *names.entry(name).or_insert(next)
            })
            .collect()
    }

    /// Whether one candidate window lies wholly inside an implementation block.
    pub(super) fn inside(&self, range: Range<usize>) -> bool {
        if self.tokens.symbols[range.clone()].contains(&self.table_plan) {
            return false;
        }
        let nested = self
            .tokens
            .depths
            .get(range.clone())
            .is_some_and(|depths| depths.iter().all(|depth| *depth > 0));
        if !nested {
            return false;
        }
        if !matches!(self.language, Language::Python | Language::Rust) {
            return true;
        }
        let Some(lines) = self.tokens.lines.get(range) else {
            return false;
        };
        self.implementation_lines.iter().any(|(opened, closed)| {
            lines
                .iter()
                .all(|line| *opened <= *line && *line <= *closed)
        })
    }

    /// Return the physical lines a token run occupies, including its block opener.
    pub(super) fn line_range(&self, range: Range<usize>) -> (usize, usize) {
        let start = range.start;
        let start_line = match start.checked_sub(1) {
            Some(previous) if self.tokens.symbols[previous] == self.block_open => {
                match self.language {
                    Language::Python => {
                        let declaration = previous
                            .checked_sub(1)
                            .expect("an indent must follow the declaration that opens its block");
                        self.tokens.lines[declaration]
                    }
                    _ => self.tokens.lines[previous],
                }
            }
            _ => self.tokens.lines[start],
        };
        (start_line, self.tokens.lines[range.end - 1])
    }

    pub(super) fn window(&self, range: Range<usize>) -> &[u32] {
        &self.tokens.symbols[range]
    }
}

/// Reduce one Rust file through the token stream its own front end would see.
fn rust(document: &Document, alphabet: &mut Alphabet) -> Option<Vec<Token>> {
    let parsed = TokenStream::from_str(&document.source).ok()?;
    let mut tokens = Vec::new();
    flatten(parsed, alphabet, &mut tokens);
    Some(tokens)
}

/// Return the source-line bounds of every Rust body that can execute.
fn rust_implementation_lines(document: &Document) -> Option<Vec<(usize, usize)>> {
    let file = syn::parse_file(&document.source).ok()?;
    let mut bodies = RustBodies::default();
    bodies.visit_file(&file);
    Some(bodies.lines)
}

#[derive(Default)]
struct RustBodies {
    lines: Vec<(usize, usize)>,
}

impl RustBodies {
    fn record(&mut self, block: &syn::Block) {
        let span = block.span();
        self.lines.push((span.start().line, span.end().line));
    }
}

impl<'ast> Visit<'ast> for RustBodies {
    fn visit_impl_item_fn(&mut self, item: &'ast syn::ImplItemFn) {
        self.record(&item.block);
        syn::visit::visit_impl_item_fn(self, item);
    }

    fn visit_item_fn(&mut self, item: &'ast syn::ItemFn) {
        self.record(&item.block);
        syn::visit::visit_item_fn(self, item);
    }

    fn visit_trait_item_fn(&mut self, item: &'ast syn::TraitItemFn) {
        if let Some(block) = &item.default {
            self.record(block);
        }
        syn::visit::visit_trait_item_fn(self, item);
    }
}

/// Write one Rust token stream out flat, keeping the delimiters that carry its nesting.
///
/// A doc comment reaches this reader as the `#[doc = "..."]` attribute the lexer already turned
/// it into, so dropping it here is what keeps the promise that a comment never decides whether
/// two items are copies. The hash and the bang that introduced the attribute go with it.
fn flatten(stream: TokenStream, alphabet: &mut Alphabet, tokens: &mut Vec<Token>) {
    let trees = stream.into_iter().collect::<Vec<_>>();
    let mut cursor = 0;
    while cursor < trees.len() {
        if let Some(line) = data_macro(&trees, cursor) {
            tokens.push(Token::plain(alphabet.id(TABLE), line));
            cursor += 3;
            continue;
        }
        let tree = trees[cursor].clone();
        cursor += 1;
        flatten_tree(tree, alphabet, tokens);
    }
}

fn flatten_tree(tree: TokenTree, alphabet: &mut Alphabet, tokens: &mut Vec<Token>) {
    let line = tree.span().start().line;
    match tree {
        TokenTree::Ident(ident) => push_rust_identifier(ident.to_string(), line, alphabet, tokens),
        TokenTree::Literal(literal) => {
            push_rust_literal(literal.to_string(), line, alphabet, tokens)
        }
        TokenTree::Punct(punct) => {
            tokens.push(Token::plain(
                alphabet.id(&punct.as_char().to_string()),
                line,
            ));
        }
        TokenTree::Group(group) if documents(&group) => remove_document_markers(alphabet, tokens),
        TokenTree::Group(group) if literal_table(&group) => {
            tokens.push(Token::plain(alphabet.id(TABLE), line));
        }
        TokenTree::Group(group) => push_rust_group(group, line, alphabet, tokens),
    }
}

fn push_rust_identifier(
    name: String,
    line: usize,
    alphabet: &mut Alphabet,
    tokens: &mut Vec<Token>,
) {
    const KEYWORDS: &[&str] = &[
        "Self", "as", "async", "await", "break", "const", "continue", "crate", "dyn", "else",
        "enum", "extern", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod", "move",
        "mut", "pub", "ref", "return", "self", "static", "struct", "super", "trait", "type",
        "union", "unsafe", "use", "where", "while",
    ];
    let token = match name.as_str() {
        "true" | "false" => Token::plain(alphabet.id(TRUTH), line),
        word if KEYWORDS.contains(&word) => Token::plain(alphabet.id(word), line),
        _ => Token::identifier(alphabet.id(IDENTIFIER), line, name),
    };
    tokens.push(token);
}

fn push_rust_literal(
    written: String,
    line: usize,
    alphabet: &mut Alphabet,
    tokens: &mut Vec<Token>,
) {
    let text = match written.starts_with(['"', '\'', 'b', 'c', 'r']) {
        true => TEXT,
        false => NUMBER,
    };
    tokens.push(Token::plain(alphabet.id(text), line));
}

fn remove_document_markers(alphabet: &mut Alphabet, tokens: &mut Vec<Token>) {
    let markers = [alphabet.id("#"), alphabet.id("!")];
    while tokens
        .last()
        .is_some_and(|token| markers.contains(&token.symbol))
    {
        tokens.pop();
    }
}

fn push_rust_group(
    group: proc_macro2::Group,
    line: usize,
    alphabet: &mut Alphabet,
    tokens: &mut Vec<Token>,
) {
    let (open, close) = match group.delimiter() {
        Delimiter::Parenthesis => ("(", ")"),
        Delimiter::Brace => ("{", "}"),
        Delimiter::Bracket => ("[", "]"),
        Delimiter::None => (INDENT, DEDENT),
    };
    tokens.push(Token::plain(alphabet.id(open), line));
    flatten(group.stream(), alphabet, tokens);
    let closing = group.span_close().start().line;
    tokens.push(Token::plain(alphabet.id(close), closing));
}

/// Whether one bracketed group is a declarative literal table rather than executable behavior.
fn literal_table(group: &proc_macro2::Group) -> bool {
    group.delimiter() == Delimiter::Bracket && group.stream().into_iter().all(literal_tree)
}

/// Whether one token-tree branch contains only literal data and its punctuation.
fn literal_tree(tree: TokenTree) -> bool {
    matches!(tree, TokenTree::Literal(_) | TokenTree::Punct(_))
        || matches!(tree, TokenTree::Group(group) if group.stream().into_iter().all(literal_tree))
}

/// Recognize a macro whose body is data rather than executable behavior.
fn data_macro(trees: &[TokenTree], at: usize) -> Option<usize> {
    match (trees.get(at), trees.get(at + 1), trees.get(at + 2)) {
        (
            Some(TokenTree::Ident(ident)),
            Some(TokenTree::Punct(bang)),
            Some(TokenTree::Group(group)),
        ) if bang.as_char() == '!'
            && (ident == "df"
                || ident == "concat" && group.stream().into_iter().all(literal_tree)) =>
        {
            Some(group.span_open().start().line)
        }
        _ => None,
    }
}
