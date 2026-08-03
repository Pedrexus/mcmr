use super::super::query_plans::polars_query_plans;
use super::super::tokens::{
    Alphabet, DEDENT, IDENTIFIER, INDENT, NEWLINE, NOTHING, NUMBER, TABLE, TEXT, TRUTH, Token,
};
use crate::discovery::Document;
use crate::source::Source;
use crate::walk::{body_range, walk};
use ruff_python_ast::{Stmt, token::TokenKind};
use ruff_python_parser::parse_module;
use ruff_text_size::{Ranged, TextRange};

pub(crate) fn python(document: &Document, alphabet: &mut Alphabet) -> Option<Vec<Token>> {
    let parsed = parse_module(&document.source).ok()?;
    let source = Source::new(document);
    let mut plans = polars_query_plans(parsed.syntax()).into_iter().peekable();
    let mut tokens = Vec::new();
    let mut written = 1;
    for token in parsed.tokens() {
        if collapse_query_plan(token.range(), &source, &mut plans, alphabet, &mut tokens) {
            continue;
        }
        let Some((text, identity)) = normalized_token(&source, *token) else {
            continue;
        };
        if !token.range().is_empty() {
            written = source.line_of(token.range().start());
        }
        tokens.push(match identity {
            Some(name) => Token::identifier(alphabet.id(text), written, name),
            None => Token::plain(alphabet.id(text), written),
        });
    }
    Some(tokens)
}

fn normalized_token(
    source: &Source,
    token: ruff_python_ast::token::Token,
) -> Option<(&str, Option<String>)> {
    match token.kind() {
        TokenKind::Comment | TokenKind::NonLogicalNewline | TokenKind::EndOfFile => None,
        TokenKind::Newline => Some((NEWLINE, None)),
        TokenKind::Indent => Some((INDENT, None)),
        TokenKind::Dedent => Some((DEDENT, None)),
        TokenKind::Name => Some((IDENTIFIER, Some(source.slice(token.range()).to_string()))),
        TokenKind::Int | TokenKind::Float | TokenKind::Complex => Some((NUMBER, None)),
        TokenKind::String
        | TokenKind::FStringStart
        | TokenKind::FStringMiddle
        | TokenKind::FStringEnd
        | TokenKind::TStringStart
        | TokenKind::TStringMiddle
        | TokenKind::TStringEnd => Some((TEXT, None)),
        TokenKind::True | TokenKind::False => Some((TRUTH, None)),
        TokenKind::None => Some((NOTHING, None)),
        _ => Some((source.slice(token.range()), None)),
    }
}

fn collapse_query_plan<I>(
    range: TextRange,
    source: &Source,
    plans: &mut std::iter::Peekable<I>,
    alphabet: &mut Alphabet,
    tokens: &mut Vec<Token>,
) -> bool
where
    I: Iterator<Item = TextRange>,
{
    while plans.peek().is_some_and(|plan| plan.end() <= range.start()) {
        plans.next();
    }
    let Some(plan) = plans.peek() else {
        return false;
    };
    if plan.start() > range.start() || range.end() > plan.end() {
        return false;
    }
    if range.start() == plan.start() {
        tokens.push(Token::plain(
            alphabet.id(TABLE),
            source.line_of(plan.start()),
        ));
    }
    true
}

pub(crate) fn implementation_lines(document: &Document) -> Option<Vec<(usize, usize)>> {
    let parsed = parse_module(&document.source).ok()?;
    let source = Source::new(document);
    Some(
        walk(parsed.syntax())
            .into_iter()
            .filter_map(|statement| match statement {
                Stmt::FunctionDef(function) => {
                    let span = source.span(body_range(&function.body));
                    Some((span.start_line, span.end_line))
                }
                _ => None,
            })
            .collect(),
    )
}
